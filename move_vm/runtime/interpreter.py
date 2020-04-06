from __future__ import annotations
from libra.access_path import AccessPath
from libra.account_address import Address
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.contract_event import ContractEvent
from libra.event import EventKey
from move_core.types.identifier import IdentStr
from libra.language_storage import ModuleId, StructTag, TypeTag
from libra.transaction import MAX_TRANSACTION_SIZE_IN_BYTES
from libra.vm_error import StatusCode, StatusType, VMStatus

from libra_vm.counters import *
from move_vm.runtime.interpreter_context import InterpreterContext
from move_vm.runtime.gas_meter import *
from move_vm.types.identifier import create_access_path, resource_storage_key
from move_vm.runtime.loaded_data import FunctionRef, FunctionReference, LoadedModule
from move_vm.runtime.runtime import VMRuntime
from move_vm.runtime.move_vm import MoveVM
from libra_vm.system_module_names import ACCOUNT_MODULE, ACCOUNT_STRUCT_NAME, EMIT_EVENT_NAME, SAVE_ACCOUNT_NAME
from vm.vm_exception import VMException, VMExceptionBase
from vm.errors import *
from vm.file_format import (
    Bytecode, FunctionHandleIndex, LocalIndex, LocalsSignatureIndex, SignatureToken,
    StructDefinitionIndex, ModuleAccess
    )
from vm.gas_schedule import (
    calculate_intrinsic_gas, AbstractMemorySize, CostTable, GasAlgebra, GasCarrier,
    NativeCostIndex
    )
from vm.file_format_common import Opcodes, SerializedType
from vm.transaction_metadata import TransactionMetadata
from move_vm.types.loaded_data import StructDef, Type
from move_vm.types.native_functions.dispatch import NativeFunction
from move_vm.types.type_context import TypeContext
from move_vm.types.values import IntegerValue, Locals, Reference, Struct, StructRef, Value
from typing import List, Optional, Mapping, Callable, Any, Tuple
from dataclasses import dataclass, field
from canoser import BoolT, Uint8, Uint64, Uint128, BytesT
from copy import deepcopy
from enum import IntEnum

def derive_type_tag(
    module: ModuleAccess,
    type_actual_tags: List[TypeTag],
    ty: SignatureToken,
) -> TypeTag:
    if ty.tag == SerializedType.BOOL:
        return TypeTag('Bool')
    elif ty.tag == SerializedType.ADDRESS:
        return TypeTag('Address')
    elif ty.tag == SerializedType.U8:
        return TypeTag('U8')
    elif ty.tag == SerializedType.U64:
        return TypeTag('U64')
    elif ty.tag == SerializedType.U128:
        return TypeTag('U128')
    elif ty.tag == SerializedType.VECTOR:
        return TypeTag('Vector', derive_type_tag(module, type_actual_tags, ty.vector_type))
    elif ty.tag == SerializedType.TYPE_PARAMETER:
        idx = ty.typeParameter
        if idx >= 0 and idx < len(type_actual_tags):
            inner = type_actual_tags[ty.typeParameter]
            return deepcopy(inner)
        else:
            raise VMException(VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION)\
                .with_message("Cannot derive type tag: type parameter index out of bounds."
                ))
    elif ty.tag == SerializedType.REFERENCE or ty.tag == SerializedType.MUTABLE_REFERENCE:
        raise VMException(VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION)\
                .with_message("Cannot derive type tag for references."))
    elif ty.tag == SerializedType.STRUCT:
        (idx, struct_type_actuals) = ty.struct
        struct_type_actuals_tags = [derive_type_tag(module, type_actual_tags, ty) \
            for ty in struct_type_actuals]
        struct_handle = module.struct_handle_at(idx)
        struct_name = module.identifier_at(struct_handle.name)
        module_handle = module.module_handle_at(struct_handle.module)
        module_address = module.address_at(module_handle.address)
        module_name = module.identifier_at(module_handle.name)
        return TypeTag('Struct', StructTag(
            address = module_address,
            module = module_name,
            name = struct_name,
            type_params = struct_type_actuals_tags,
        ))


# `Interpreter` instances can execute Move functions.
#
# An `Interpreter` instance is a stand alone execution context for a function.
# It mimics execution on a single thread, with an call stack and an operand stack.
# The `Interpreter` receives a reference to a data store used by certain opcodes
# to do operations on data on chain and a `TransactionMetadata` which is also used to resolve
# specific opcodes.
# A `ModuleCache` is also provided to resolve external references to code.
# REVIEW: abstract the data store better (maybe a single Trait for both data and event?)
# The ModuleCache should be a Loader with a proper API.
# Resolve where GasMeter should live.
@dataclass
class Interpreter:
    # Operand stack, where Move `Value`s are stored for stack operations.
    operand_stack: Stack
    # The stack of active functions.
    call_stack: CallStack
    # Transaction data to resolve special bytecodes (e.g. GetTxnSequenceNumber, GetTxnPublicKey,
    # GetTxnSenderAddress, ...)
    txn_data: TransactionMetadata
    gas_schedule: CostTable
    enable_gas: bool = False


    # Execute a function.
    # `module` is an identifier for the name the module is stored in. `function_name` is the name
    # of the function. If such function is found, the VM will execute this function with arguments
    # `args`. The return value will be placed on the top of the value stack and abort if an error
    # occurs.
    # REVIEW: this should probably disappear or at the very least only one between
    # `execute_function` and `entrypoint` should exist. It's a bit messy at
    # the moment given tooling and testing. Once we remove Program transactions and we
    # clean up the loader we will have a better time cleaning this up.
    def execute_function(
        context: InterpreterContext,
        runtime: VMRuntime,
        txn_data: TransactionMetadata,
        gas_schedule: CostTable,
        module: ModuleId,
        function_name: IdentStr,
        args: List[Value],
    ) -> None:
        # print(f"{module.name}.{function_name}")
        interp = Interpreter.new(txn_data, gas_schedule)
        loaded_module = runtime.get_loaded_module(module, context)
        func_idx = loaded_module\
            .function_defs_table\
            .get(function_name)
            #.ok_or_else(|| VMStatus(StatusCode.LINKER_ERROR))
        func = FunctionRef.new(loaded_module, func_idx)
        interp.execute(runtime, context, func, args)


    # Entrypoint into the interpreter. All external calls need to be routed through this
    # function.
    def entrypoint(
        context: InterpreterContext,
        runtime: VMRuntime,
        txn_data: TransactionMetadata,
        gas_schedule: CostTable,
        func: FunctionRef,
        args: List[Value],
    ) -> None:
        # We charge an intrinsic amount of gas based upon the size of the transaction submitted
        # (in raw bytes).
        txn_size = txn_data.transaction_size
        # The callers of this function verify the transaction before executing it. Transaction
        # verification ensures the following condition.
        assert (txn_size.get() <= (MAX_TRANSACTION_SIZE_IN_BYTES))
        # We count the intrinsic cost of the transaction here, since that needs to also cover the
        # setup of the function.
        interp = Interpreter.new(txn_data, gas_schedule)
        gas_consume(context, calculate_intrinsic_gas(txn_size))
        interp.execute(runtime, context, func, args)



    # Create a new instance of an `Interpreter` in the context of a transaction with a
    # given module cache and gas schedule.
    @classmethod
    def new(cls, txn_data: TransactionMetadata, gas_schedule: CostTable) -> Interpreter:
        return Interpreter(
            Stack(),
            CallStack(),
            txn_data,
            gas_schedule,
        )


    # Internal execution entry point.
    def execute(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        function: FunctionRef,
        args: List[Value],
    ) -> None:
        # No unwinding of the call stack and value stack need to be done here -- the context will
        # take care of that.
        self.execute_main(runtime, context, function, args, 0)


    # Main loop for the execution of a function.
    #
    # This function sets up a `Frame` and calls `execute_code_unit` to execute code of the
    # function represented by the frame. Control comes back to this function on return or
    # on call. When that happens the frame is changes to a new one (call) or to the one
    # at the top of the stack (return). If the call stack is empty execution is completed.
    # REVIEW: create account will be removed in favor of a native function (no opcode) and
    # we can simplify this code quite a bit.
    def execute_main(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        function: FunctionRef,
        args: List[Value],
        create_account_marker: usize,
    ) -> None:
        locls = Locals.new(function.local_count())
        # TODO: assert consistency of args and function formals
        for (i, value) in enumerate(args):
            locls.store_loc(i, value)

        current_frame = Frame.new(function, [], [], locls)
        while True:
            code = current_frame.code_definition()
            exit_code = self\
                .execute_code_unit(runtime, context, current_frame, code)
                #.or_else(|err| Err(self.maybe_core_dump(err, &current_frame)))

            if exit_code.tag == ExitCodeTag.Return:
                # TODO: assert consistency of current frame: stack height correct
                if create_account_marker == self.call_stack.v0.__len__():
                    return

                current_frame = self.call_stack.pop()
                if not current_frame:
                    raise VMException(self.unreachable("call stack cannot be empty", current_frame))

            elif exit_code.tag == ExitCodeTag.Call:
                (idx, type_actuals_idx) = exit_code.value
                type_actuals_sig = current_frame.module()\
                    .locals_signature_at(type_actuals_idx).v0
                gas_instr(context,
                    self,
                    Opcodes.CALL,
                    AbstractMemorySize.new(type_actuals_sig.__len__() + 1)
                )
                def lambda_derive_type_tag(ty):
                    return derive_type_tag(
                            current_frame.module(),
                            current_frame.type_actual_tags,
                            ty,
                        )
                type_actual_tags = [lambda_derive_type_tag(ty) for ty in type_actuals_sig]
                type_context = TypeContext(current_frame.type_actuals)
                def lambda_resolve_signature_token(ty):
                    return runtime.resolve_signature_token(
                            current_frame.module(),
                            ty,
                            type_context,
                            context,
                        )
                type_actuals = [lambda_resolve_signature_token(ty) for ty in type_actuals_sig]

                opt_frame = self.make_call_frame(
                        runtime,
                        context,
                        current_frame.module(),
                        idx,
                        type_actual_tags,
                        type_actuals,
                    )
                    #.or_else(|err| Err(self.maybe_core_dump(err, &current_frame)))
                if opt_frame is not None:
                    self.call_stack.push(current_frame)
                    current_frame = opt_frame


    # Execute a Move function until a return or a call opcode is found.
    def execute_code_unit(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        frame: Frame,
        code: List[Bytecode],
    ) -> ExitCode:
        # TODO: re-enbale this once gas metering is sorted out
        #code = frame.code_definition()
        while True:
            for instruction in code[frame.pc:]:
                # print(f"PC[{frame.pc}] -> {instruction}")
                frame.pc += 1
                if instruction.tag == Opcodes.POP:
                    gas_const_instr(context, self, Opcodes.POP)
                    self.operand_stack.pop()

                elif instruction.tag == Opcodes.RET:
                    gas_const_instr(context, self, Opcodes.RET)
                    return ExitCode.Return()

                elif instruction.tag == Opcodes.BR_TRUE:
                    offset = instruction.value
                    gas_const_instr(context, self, Opcodes.BR_TRUE)
                    if self.operand_stack.pop_as(BoolT):
                        frame.pc = offset
                        break

                elif instruction.tag == Opcodes.BR_FALSE:
                    offset = instruction.value
                    gas_const_instr(context, self, Opcodes.BR_FALSE)
                    if not self.operand_stack.pop_as(BoolT):
                        frame.pc = offset
                        break

                elif instruction.tag == Opcodes.BRANCH:
                    offset = instruction.value
                    gas_const_instr(context, self, Opcodes.BRANCH)
                    frame.pc = offset
                    break

                elif instruction.tag == Opcodes.LD_U8:
                    int_const = instruction.value
                    gas_const_instr(context, self, Opcodes.LD_U8)
                    self.operand_stack.push(Value.Uint8(int_const))

                elif instruction.tag == Opcodes.LD_U64:
                    int_const = instruction.value
                    gas_const_instr(context, self, Opcodes.LD_U64)
                    self.operand_stack.push(Value.Uint64(int_const))

                elif instruction.tag == Opcodes.LD_U128:
                    int_const = instruction.value
                    gas_const_instr(context, self, Opcodes.LD_U128)
                    self.operand_stack.push(Value.Uint128(int_const))

                elif instruction.tag == Opcodes.LD_ADDR:
                    idx = instruction.value
                    gas_const_instr(context, self, Opcodes.LD_ADDR)
                    self.operand_stack\
                        .push(Value.address(frame.module().address_at(idx)))

                elif instruction.tag == Opcodes.LD_BYTEARRAY:
                    idx = instruction.value
                    v = frame.module().byte_array_at(idx)
                    gas_instr(context,
                        self,
                        Opcodes.LD_BYTEARRAY,
                        AbstractMemorySize.new(v.__len__())
                    )
                    self.operand_stack\
                        .push(Value.vector_u8(bytes(v)))

                elif instruction.tag == Opcodes.LD_TRUE:
                    gas_const_instr(context, self, Opcodes.LD_TRUE)
                    self.operand_stack.push(Value.bool(True))

                elif instruction.tag == Opcodes.LD_FALSE:
                    gas_const_instr(context, self, Opcodes.LD_FALSE)
                    self.operand_stack.push(Value.bool(False))

                elif instruction.tag == Opcodes.COPY_LOC:
                    idx = instruction.value
                    local = frame.copy_loc(idx)
                    gas_instr(context, self, Opcodes.COPY_LOC, local.size())
                    self.operand_stack.push(local)

                elif instruction.tag == Opcodes.MOVE_LOC:
                    idx = instruction.value
                    local = frame.move_loc(idx)
                    gas_instr(context, self, Opcodes.MOVE_LOC, local.size())
                    self.operand_stack.push(local)

                elif instruction.tag == Opcodes.ST_LOC:
                    idx = instruction.value
                    value_to_store = self.operand_stack.pop()
                    gas_instr(context, self, Opcodes.ST_LOC, value_to_store.size())
                    frame.store_loc(idx, value_to_store)

                elif instruction.tag == Opcodes.CALL:
                    (idx, type_actuals_idx) = instruction.value
                    return ExitCode.Call(idx, type_actuals_idx)

                elif instruction.tag == Opcodes.MUT_BORROW_LOC or\
                        instruction.tag == Opcodes.IMM_BORROW_LOC :
                    idx = instruction.value
                    gas_const_instr(context, self, instruction.tag)
                    self.operand_stack.push(frame.borrow_loc(idx))

                elif instruction.tag == Opcodes.MUT_BORROW_FIELD or\
                        instruction.tag == Opcodes.IMM_BORROW_FIELD:
                    fd_idx = instruction.value
                    gas_const_instr(context, self, instruction.tag)
                    field_offset = frame.module().get_field_offset(fd_idx)
                    reference = self.operand_stack.pop_as(StructRef)
                    field_ref = reference.borrow_field(field_offset)
                    self.operand_stack.push(field_ref)

                elif instruction.tag == Opcodes.PACK:
                    (sd_idx, _) = instruction.value
                    struct_def = frame.module().struct_def_at(sd_idx)
                    field_count = struct_def.declared_field_count()
                    args = self.operand_stack.popn(field_count)
                    size = AbstractMemorySize.new(field_count)
                    for v in args:
                        size.add(v.size())

                    gas_instr(context, self, Opcodes.PACK, size)
                    self.operand_stack.push(Value.struct_(Struct.pack(args)))

                elif instruction.tag == Opcodes.UNPACK:
                    (sd_idx, _) = instruction.value
                    struct_def = frame.module().struct_def_at(sd_idx)
                    field_count = struct_def.declared_field_count()
                    struct_ = self.operand_stack.pop_as(Struct)
                    gas_instr(context,
                        self,
                        Opcodes.UNPACK,
                        AbstractMemorySize.new(field_count),
                    )
                    # TODO: Whether or not we want this gas metering in the loop is
                    # questionable.  However, if we don't have it in the loop we could wind up
                    # doing a fair bit of work before charging for it.
                    for value in struct_.unpack():
                        gas_instr(context, self, Opcodes.UNPACK, value.size())
                        self.operand_stack.push(value)

                elif instruction.tag == Opcodes.READ_REF:
                    reference = self.operand_stack.pop_as(Reference)
                    value = reference.read_ref()
                    gas_instr(context, self, Opcodes.READ_REF, value.size())
                    self.operand_stack.push(value)

                elif instruction.tag == Opcodes.WRITE_REF:
                    reference = self.operand_stack.pop_as(Reference)
                    value = self.operand_stack.pop()
                    gas_instr(context, self, Opcodes.WRITE_REF, value.size())
                    reference.write_ref(value)

                elif instruction.tag == Opcodes.CAST_U8:
                    gas_const_instr(context, self, Opcodes.CAST_U8)
                    integer_value = self.operand_stack.pop_as(IntegerValue)
                    self.operand_stack.push(Value.Uint8(integer_value.cast(Uint8)))

                elif instruction.tag == Opcodes.CAST_U64:
                    gas_const_instr(context, self, Opcodes.CAST_U64)
                    integer_value = self.operand_stack.pop_as(IntegerValue)
                    self.operand_stack.push(Value.Uint64(integer_value.cast(Uint64)))

                elif instruction.tag == Opcodes.CAST_U128:
                    gas_const_instr(context, self, Opcodes.CAST_U128)
                    integer_value = self.operand_stack.pop_as(IntegerValue)
                    self.operand_stack.push(Value.Uint128(integer_value.cast(Uint128)))

                    # Arithmetic Operations
                elif instruction.tag == Opcodes.ADD:
                    gas_const_instr(context, self, Opcodes.ADD)
                    self.binop_int(IntegerValue.add_checked)

                elif instruction.tag == Opcodes.SUB:
                    gas_const_instr(context, self, Opcodes.SUB)
                    self.binop_int(IntegerValue.sub_checked)

                elif instruction.tag == Opcodes.MUL:
                    gas_const_instr(context, self, Opcodes.MUL)
                    self.binop_int(IntegerValue.mul_checked)

                elif instruction.tag == Opcodes.MOD:
                    gas_const_instr(context, self, Opcodes.MOD)
                    self.binop_int(IntegerValue.rem_checked)

                elif instruction.tag == Opcodes.DIV:
                    gas_const_instr(context, self, Opcodes.DIV)
                    self.binop_int(IntegerValue.div_checked)

                elif instruction.tag == Opcodes.BIT_OR:
                    gas_const_instr(context, self, Opcodes.BIT_OR)
                    self.binop_int(IntegerValue.bit_or)

                elif instruction.tag == Opcodes.BIT_AND:
                    gas_const_instr(context, self, Opcodes.BIT_AND)
                    self.binop_int(IntegerValue.bit_and)

                elif instruction.tag == Opcodes.XOR:
                    gas_const_instr(context, self, Opcodes.XOR)
                    self.binop_int(IntegerValue.bit_xor)

                elif instruction.tag == Opcodes.SHL:
                    gas_const_instr(context, self, Opcodes.SHL)
                    rhs = self.operand_stack.pop_as(Uint8)
                    lhs = self.operand_stack.pop_as(IntegerValue)
                    self.operand_stack.push(lhs.shl_checked(rhs).into_value())

                elif instruction.tag == Opcodes.SHR:
                    gas_const_instr(context, self, Opcodes.SHR)
                    rhs = self.operand_stack.pop_as(Uint8)
                    lhs = self.operand_stack.pop_as(IntegerValue)
                    self.operand_stack.push(lhs.shr_checked(rhs).into_value())

                elif instruction.tag == Opcodes.OR:
                    gas_const_instr(context, self, Opcodes.OR)
                    self.binop_bool(lambda l, r: l or r, BoolT)

                elif instruction.tag == Opcodes.AND:
                    gas_const_instr(context, self, Opcodes.AND)
                    self.binop_bool(lambda l, r: l and r, BoolT)

                elif instruction.tag == Opcodes.LT:
                    gas_const_instr(context, self, Opcodes.LT)
                    self.binop_bool(IntegerValue.lt)

                elif instruction.tag == Opcodes.GT:
                    gas_const_instr(context, self, Opcodes.GT)
                    self.binop_bool(IntegerValue.gt)

                elif instruction.tag == Opcodes.LE:
                    gas_const_instr(context, self, Opcodes.LE)
                    self.binop_bool(IntegerValue.le)

                elif instruction.tag == Opcodes.GE:
                    gas_const_instr(context, self, Opcodes.GE)
                    self.binop_bool(IntegerValue.ge)

                elif instruction.tag == Opcodes.ABORT:
                    # breakpoint()
                    #context.data_view.data_cache.data_view.print_account_resource(True)
                    gas_const_instr(context, self, Opcodes.ABORT)
                    error_code = self.operand_stack.pop_as(Uint64)
                    raise VMException(VMStatus(StatusCode.ABORTED).with_sub_status(error_code))

                elif instruction.tag == Opcodes.EQ:
                    lhs = self.operand_stack.pop()
                    rhs = self.operand_stack.pop()
                    gas_instr(context,
                        self,
                        Opcodes.EQ,
                        lhs.size().add(rhs.size())
                    )
                    self.operand_stack.push(Value.bool(lhs.equals(rhs)))

                elif instruction.tag == Opcodes.NEQ:
                    lhs = self.operand_stack.pop()
                    rhs = self.operand_stack.pop()
                    gas_instr(context,
                        self,
                        Opcodes.NEQ,
                        lhs.size().add(rhs.size())
                    )
                    self.operand_stack.push(Value.bool(not lhs.equals(rhs)))

                elif instruction.tag == Opcodes.GET_TXN_SENDER:
                    gas_const_instr(context, self, Opcodes.GET_TXN_SENDER)
                    self.operand_stack.push(Value.address(self.txn_data.sender))

                elif instruction.tag == Opcodes.MUT_BORROW_GLOBAL or\
                        instruction.tag == Opcodes.IMM_BORROW_GLOBAL:
                    (idx, type_actuals_idx) = instruction.value
                    addr = self.operand_stack.pop_as(Address)
                    size = self.global_data_op(
                        runtime,
                        context,
                        addr,
                        idx,
                        type_actuals_idx,
                        frame,
                        Interpreter.borrow_global,
                    )
                    gas_instr(context, self, Opcodes.MUT_BORROW_GLOBAL, size)

                elif instruction.tag == Opcodes.EXISTS:
                    (idx, type_actuals_idx) = instruction.value
                    addr = self.operand_stack.pop_as(Address)
                    size = self.global_data_op(
                        runtime,
                        context,
                        addr,
                        idx,
                        type_actuals_idx,
                        frame,
                        Interpreter.exists,
                    )
                    gas_instr(context, self, Opcodes.EXISTS, size)

                elif instruction.tag == Opcodes.MOVE_FROM:
                    (idx, type_actuals_idx) = instruction.value
                    addr = self.operand_stack.pop_as(Address)
                    size = self.global_data_op(
                        runtime,
                        context,
                        addr,
                        idx,
                        type_actuals_idx,
                        frame,
                        Interpreter.move_from,
                    )
                    # TODO: Have this calculate before pulling in the data based upon
                    # the size of the data that we are about to read in.
                    gas_instr(context, self, Opcodes.MOVE_FROM, size)

                elif instruction.tag == Opcodes.MOVE_TO:
                    (idx, type_actuals_idx) = instruction.value
                    addr = self.txn_data.sender
                    size = self.global_data_op(
                        runtime,
                        context,
                        addr,
                        idx,
                        type_actuals_idx,
                        frame,
                        Interpreter.move_to_sender,
                    )
                    gas_instr(context, self, Opcodes.MOVE_TO, size)

                elif instruction.tag == Opcodes.FREEZE_REF:
                    pass
                    # FreezeRef should just be a null op as we don't distinguish between mut
                    # and immut ref at runtime.

                elif instruction.tag == Opcodes.NOT:
                    gas_const_instr(context, self, Opcodes.NOT)
                    value = not self.operand_stack.pop_as(BoolT)
                    self.operand_stack.push(Value.bool(value))

                else:
                    raise VMException(VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION)\
                        .with_message("This opcode is deprecated and will be removed soon"))

            # ok we are out, it's a branch, check the pc for good luck
            # TODO: re-work the logic here. Cost synthesis and tests should have a more
            # natural way to plug in
            if frame.pc >= code.__len__():
                # if cfg!(test) || cfg!(feature = "instruction_synthesis") {
                #     # In order to test the behavior of an instruction stream, hitting end of the
                #     # code should report no error so that we can check the
                #     # locals.
                #     return ExitCode.Return
                # else:
                raise VMException(VMStatus(StatusCode.PC_OVERFLOW))


    # Returns a `Frame` if the call is to a Move function. Calls to native functions are
    # "inlined" and this returns `None`.
    #
    # Native functions do not push a frame at the moment and as such errors from a native
    # function are incorrectly attributed to the caller.
    def make_call_frame(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        module: LoadedModule,
        idx: FunctionHandleIndex,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
    ) -> Optional[Frame]:
        func = runtime.resolve_function_ref(module, idx, context)
        if func.is_native():
            self.call_native(runtime, context, func, type_actual_tags, type_actuals)
            return None
        else:
            locls = Locals.new(func.local_count())
            arg_count = func.arg_count()
            for i in range(arg_count):
                locls.store_loc(arg_count - i - 1, self.operand_stack.pop())

            return Frame.new(
                func,
                type_actual_tags,
                type_actuals,
                locls,
            )


    # Call a native functions.
    def call_native(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        function: FunctionRef,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
    ) -> None:
        module = function.module()
        module_id = module.self_id()
        function_name = function.name()
        import move_vm
        native_function = move_vm.types.native_functions.dispatch.resolve_native_function(module_id, function_name)
        # native_function = NativeFunction.resolve(module_id, function_name)
            #.ok_or_else(|| VMStatus(StatusCode.LINKER_ERROR))
        if module_id == ACCOUNT_MODULE and function_name == EMIT_EVENT_NAME:
            self.call_emit_event(context, type_actual_tags, type_actuals)
        elif module_id == ACCOUNT_MODULE and function_name == SAVE_ACCOUNT_NAME:
            self.call_save_account(runtime, context, type_actual_tags, type_actuals)
        else:
            arguments = []
            expected_args = native_function.num_args()
            # REVIEW: this is checked again in every functions, rationalize it!
            if function.arg_count() != expected_args:
                # Should not be possible due to bytecode verifier but this
                # assertion is here to make sure
                # the view the type checker had lines up with the
                # execution of the native function
                raise VMException(VMStatus(StatusCode.LINKER_ERROR))

            for _ in range(expected_args):
                arguments.insert(0, self.operand_stack.pop())

            result =\
                native_function.dispatch(type_actual_tags, arguments, self.gas_schedule)

            gas_consume(context, result.cost)
            if isinstance(result.result, list):
                for value in result.result:
                    self.operand_stack.push(value)
            elif isinstance(result.result, VMStatus):
                raise VMException(result.result)
            else:
                bail("unreachable!")



    # Emit an event if the native function was `write_to_event_store`.
    def call_emit_event(
        self,
        context: InterpreterContext,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
    ) -> None:
        if type_actual_tags.__len__() != 1:
            raise VMException(
                VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION).with_message(format_str(
                    "write_to_event_storage expects 1 argument got {}.",
                    type_actual_tags.__len__()
                )),
            )


        if type_actuals.__len__() != 1:
            raise VMException(
                VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION).with_message(format_str(
                    "write_to_event_storage expects 1 argument got {}.",
                    type_actuals.__len__()
                )),
            )


        type_tag = type_actual_tags.pop()
        layout = type_actuals.pop()

        event_data = self.operand_stack.pop()
        msg = event_data.simple_serialize(layout)
            #.ok_or_else(|| VMStatus(StatusCode.DATA_FORMAT_ERROR))
        count = self.operand_stack.pop_as(Uint64)
        guid = self.operand_stack.pop_as(bytes)
        context.push_event(ContractEvent(guid, count, type_tag, msg))

    # Save an account into the data store.
    def call_save_account(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
    ) -> None:
        gas_consume(context,
            self.gas_schedule.native_cost(NativeCostIndex.SAVE_ACCOUNT).total()
        )
        account_module = runtime.get_loaded_module(ACCOUNT_MODULE, context)
        address = self.operand_stack.pop_as(Address)
        if Address.equal_address(address, CORE_CODE_ADDRESS):
            raise VMException(VMStatus(StatusCode.CREATE_NULL_ACCOUNT))

        Interpreter.save_under_address(
            runtime,
            context,
            [],
            [],
            account_module,
            account_config.ACCOUNT_STRUCT_NAME,
            self.operand_stack.pop_as(Struct),
            address,
        )
        Interpreter.save_under_address(
            runtime,
            context,
            [type_actual_tags[0]],
            type_actuals,
            account_module,
            account_config.ACCOUNT_BALANCE_STRUCT_NAME,
            self.operand_stack.pop_as(Struct),
            address,
        )

    # Perform a binary operation to two values at the top of the stack.
    def binop(self, f, T) -> None:
        rhs = self.operand_stack.pop_as(T)
        lhs = self.operand_stack.pop_as(T)
        result = f(lhs, rhs)
        self.operand_stack.push(result)


    # Perform a binary operation for integer values.
    def binop_int(self, f) -> None:
        def lambda_f(lhs, rhs):
            ret = f(lhs, rhs)
            return Value(ret.enum_name, ret.value)
        self.binop(lambda_f, IntegerValue)

    # Perform a binary operation for boolean values.
    def binop_bool(self, f, T=IntegerValue) -> None:
        rhs = self.operand_stack.pop_as(T)
        lhs = self.operand_stack.pop_as(T)
        b = f(lhs, rhs)
        result = Value('Bool', b)
        self.operand_stack.push(result)


    # Entry point for all global store operations (effectively opcodes).
    #
    # This performs common operation on the data store and then executes the specific
    # opcode.
    def global_data_op(
        self,
        runtime: VMRuntime,
        context: InterpreterContext,
        address: Address,
        idx: StructDefinitionIndex,
        type_actuals_idx: LocalsSignatureIndex,
        frame: Frame,
        op: Callable,
    ) -> AbstractMemorySize:
        module = frame.module()
        type_actuals_sig = frame.module().locals_signature_at(type_actuals_idx).v0
        type_actual_tags = [derive_type_tag(frame.module(), frame.type_actual_tags, ty)\
            for ty in type_actuals_sig]

        type_context = TypeContext(frame.type_actuals)
        type_actuals = [runtime.resolve_signature_token(frame.module(), ty, type_context, context)\
            for ty in type_actuals_sig]

        ap = Interpreter.make_access_path(module, idx, type_actual_tags, address)
        struct_def = runtime.resolve_struct_def(module, idx, type_actuals, context)
        return op(self, context, ap, struct_def)


    # BorrowGlobal (mutable and not) opcode.
    def borrow_global(
        self,
        context: InterpreterContext,
        ap: AccessPath,
        struct_def: StructDef,
    ) -> AbstractMemorySize:
        g = context.borrow_global(ap, struct_def)
        size = g.size()
        self.operand_stack.push(g.borrow_global())
        return size


    # Exists opcode.
    def exists(
        self,
        context: InterpreterContext,
        ap: AccessPath,
        struct_def: StructDef,
    ) -> AbstractMemorySize:
        (exists, mem_size) = context.resource_exists(ap, struct_def)
        # if not exists:
        #     breakpoint()
        self.operand_stack.push(Value('Bool', exists))
        return mem_size


    # MoveFrom opcode.
    def move_from(
        self,
        context: InterpreterContext,
        ap: AccessPath,
        struct_def: StructDef,
    ) -> AbstractMemorySize:
        resource = context.move_resource_from(ap, struct_def)
        size = resource.size()
        self.operand_stack.push(resource)
        return size


    # MoveToSender opcode.
    def move_to_sender(
        self,
        context: InterpreterContext,
        ap: AccessPath,
        struct_def: StructDef,
    ) -> AbstractMemorySize:
        resource = self.operand_stack.pop_as(Struct)
        size = resource.size()
        context.move_resource_to(ap, struct_def, resource)
        return size


    # Helper to create a resource storage key (`AccessPath`) for global storage operations.
    def make_access_path(
        module: ModuleAccess,
        idx: StructDefinitionIndex,
        type_actual_tags: List[TypeTag],
        address: Address,
    ) -> AccessPath:
        struct_tag = resource_storage_key(module, idx, type_actual_tags)
        return create_access_path(address, struct_tag)

    # Save a resource under the address specified by `account_address`
    @classmethod
    def save_under_address(cls,
        runtime: VMRuntime,
        context: InterpreterContext,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
        module: LoadedModule,
        struct_name: IdentStr,
        resource_to_save: Struct,
        account_address: Address,
    ) -> None:
        struct_id = module.struct_defs_table.get(struct_name)
        struct_def = runtime.resolve_struct_def(module, struct_id, type_actuals, context)
        path = Interpreter.make_access_path(module, struct_id, type_actual_tags, account_address)
        context.move_resource_to(path, struct_def, resource_to_save)


    # Debugging and logging helpers.


    # Given an `VMStatus` generate a core dump if the error is an `InvariantViolation`.
    def maybe_core_dump(
        self,
        err: VMStatus,
        current_frame: Frame,
    ) -> VMStatus:
        # a verification error cannot happen at runtime so change it into an invariant violation.
        if err.status_type() == StatusType.Verification:
            logger.critical("Verification error during runtime: {}", err)
            new_err = VMStatus(StatusCode.VERIFICATION_ERROR)
            new_err.message = err.message
            err = new_err
        elif err.status_type() == StatusType.InvariantViolation:
            state = self.get_internal_state(current_frame)
            logger.critical(
                "Error: {}\nCORE DUMP: >>>>>>>>>>>>\n{}\n<<<<<<<<<<<<\n",
                err,
                state,
            )
        return err


    # Generate a string which is the status of the interpreter: call stack, current bytecode
    # stream, locals and operand stack.
    #
    # It is used when generating a core dump but can be used for debugging of the interpreter.
    # It will be exposed via a debug module to give developers a way to print the internals
    # of an execution.
    def get_internal_state(self, current_frame: Frame) -> str:
        internal_state = "Call stack:\n"
        for (i, frame) in enumerate(self.call_stack.v0):
            internal_state += format_str(
                    " frame #{}: {} [pc = {}]\n",
                    i,
                    frame.function.pretty_string(),
                    frame.pc,
                )


        internal_state += format_str(
                "*frame #{}: {} [pc = {}]:\n",
                self.call_stack.v0.__len__(),
                current_frame.function.pretty_string(),
                current_frame.pc,
            )

        code = current_frame.code_definition()
        pc = current_frame.pc
        if pc < code.__len__():
            i = 0
            for bytecode in code[0:pc]:
                internal_state.push_str(format_str("{}> {}\n", i, bytecode))
                i += 1

            internal_state.push_str(format_str("{}* {}\n", i, code[pc]))

        internal_state.push_str(format_str("Locals:\n{}", current_frame.locals))
        internal_state.push_str("Operand Stack:\n")
        for value in self.operand_stack.v0:
            internal_state.push_str(format_str("{}\n", value))

        return internal_state


    # Generate a core dump and an `UNREACHABLE` invariant violation.
    def unreachable(self, msg: str, current_frame: Frame) -> VMStatus:
        err = VMStatus(StatusCode.UNREACHABLE).with_message(msg)
        return self.maybe_core_dump(err, current_frame)


# TODO Determine stack size limits based on gas limit
OPERAND_STACK_SIZE_LIMIT: usize = 1024
CALL_STACK_SIZE_LIMIT: usize = 1024

# The operand stack.
@dataclass
class Stack:
    v0: List[Value] = field(default_factory=list)

    # Push a `Value` on the stack if the max stack size has not been reached. Abort execution
    # otherwise.
    def push(self, value: Value) -> None:
        if not isinstance(value, Value):
            bail(f"{value} is not a Value class.")
        if self.v0.__len__() < OPERAND_STACK_SIZE_LIMIT:
            self.v0.append(value)
        else:
            raise VMException(VMStatus(StatusCode.EXECUTION_STACK_OVERFLOW))


    # Pop a `Value` off the stack or abort execution if the stack is empty.
    def pop(self) -> Value:
        return self.v0.pop()


    # Pop a `Value` of a given type off the stack. Abort if the value is not of the given
    # type or if the stack is empty.
    def pop_as(self, ty):
        if ty == bool:
            ty = BoolT
        elif ty == bytes:
            ty = BytesT()
        value = self.pop()
        return value.value_as(ty)


    # Pop n values off the stack.
    def popn(self, n: Uint16) -> List[Value]:
        if len(self.v0) < n:
            raise VMException(VMStatus(StatusCode.EMPTY_VALUE_STACK))

        remaining_stack_size = len(self.v0) - n
        ret = self.v0[remaining_stack_size:]
        self.v0 = self.v0[0:remaining_stack_size]
        return ret


@dataclass
class VMFrameException(VMExceptionBase):
    frame: Frame

# A call stack.
@dataclass
class CallStack:
    v0: List[Frame] = field(default_factory=list)

    # Push a `Frame` on the call stack.
    def push(
        self,
        frame: Frame,
    ):
        if self.v0.__len__() < CALL_STACK_SIZE_LIMIT:
            self.v0.append(frame)
        else:
            raise VMFrameException(frame)

    # Pop a `Frame` off the call stack.
    def pop(self) -> Optional[Frame]:
        return self.v0.pop()


# A `Frame` is the execution context for a function. It holds the locals of the function and
# the function itself.
@dataclass
class Frame:
    pc: Uint16
    locls: Locals
    function: FunctionReference
    type_actual_tags: List[TypeTag]
    type_actuals: List[Type]


    # Create a new `Frame` given a `FunctionReference` and the function `Locals`.
    #
    # The locals must be loaded before calling this.
    @classmethod
    def new(cls,
        function: FunctionReference,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
        locls: Locals,
    ) -> Frame:
        return Frame(
            0,
            locls,
            function,
            type_actual_tags,
            type_actuals,
        )

    # Return the code stream of this function.
    def code_definition(self) -> List[Bytecode]:
        return self.function.code_definition()


    # Return the `LoadedModule` this function lives in.
    def module(self) -> LoadedModule:
        return self.function.module()


    # Copy a local from this frame at the given index. Return an error if the index is
    # out of bounds or the local is `Invalid`.
    def copy_loc(self, idx: LocalIndex) -> Value:
        return self.locls.copy_loc(idx)


    # Move a local from this frame at the given index. Return an error if the index is
    # out of bounds or the local is `Invalid`.
    def move_loc(self, idx: LocalIndex) -> Value:
        return self.locls.move_loc(idx)


    # Store a `Value` into a local at the given index. Return an error if the index is
    # out of bounds.
    def store_loc(self, idx: LocalIndex, value: Value) -> None:
        if not isinstance(value, Value):
            bail(f"{value} is not a Value class.")
        self.locls.store_loc(idx, value)

    # Borrow a local from this frame at the given index. Return an error if the index is
    # out of bounds or the local is `Invalid`.
    def borrow_loc(self, idx: LocalIndex) -> Value:
        return self.locls.borrow_loc(idx)


class ExitCodeTag(IntEnum):
    Return = 0
    Call = 1

# An `ExitCode` from `execute_code_unit`.
@dataclass
class ExitCode:
    tag: ExitCodeTag
    value: Tuple[FunctionHandleIndex, LocalsSignatureIndex] = None

    # A `Return` opcode was found.
    @classmethod
    def Return(cls):
        return ExitCode(ExitCodeTag.Return)

    # A `Call` opcode was found.
    @classmethod
    def Call(cls, findex, lsindex):
        return ExitCode(ExitCodeTag.Call, (findex, lsindex))



# Below are all the functions needed for gas synthesis and gas cost.
# The story is going to change given those functions expose internals of the Interpreter that
# should never leak out.
# For now they are grouped in a couple of temporary class and impl that can be used
# to determine what the needs of gas logic has to be.

#[cfg(any(test, feature = "instruction_synthesis"))]
@dataclass
class InterpreterForCostSynthesis:
    interpreter: Interpreter


    def new(txn_data: TransactionMetadata, gas_schedule: CostTable) -> InterpreterForCostSynthesis:
        interpreter = Interpreter.new(txn_data, gas_schedule)
        return InterpreterForCostSynthesis(interpreter)


    def set_stack(self, stack: List[Value]):
        self.interpreter.operand_stack.v0 = stack


    def call_stack_height(self) -> usize:
        return self.interpreter.call_stack.v0.__len__()


    def pop_call(self):
        self.interpreter.call_stack.pop()

    def push_frame(
        self,
        func: FunctionRef,
        type_actual_tags: List[TypeTag],
        type_actuals: List[Type],
    ):
        count = func.local_count()
        self.interpreter.call_stack.push(
            Frame.new(
                func,
                type_actual_tags,
                type_actuals,
                Locals.new(count),
            ))


    def load_call(self, args: Mapping[LocalIndex, Value]):
        current_frame = self.interpreter.call_stack.pop()
        for (local_index, local) in args:
            current_frame.store_loc(local_index, local)

        self.interpreter.call_stack.push(current_frame)


    def execute_code_snippet(
        self,
        move_vm: MoveVM,
        context: InterpreterContext,
        code: List[Bytecode],
    ) -> None:
        current_frame = self.interpreter.call_stack.pop()
        self.interpreter\
            .execute_code_unit(move_vm.runtime, context, current_frame, code)
        self.interpreter.call_stack.push(current_frame)


