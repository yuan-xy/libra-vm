from __future__ import annotations
from bytecode_verifier.absint import (
    AbstractInterpreter, BlockInvariant, BlockPostcondition, BlockPrecondition,
    TransferFunctions
)
from bytecode_verifier.abstract_state import AbstractState, AbstractValue, TypedAbstractValue
from bytecode_verifier.control_flow_graph import VMControlFlowGraph
from bytecode_verifier.ref_id import RefID

from libra.vm_error import StatusCode, VMStatus

from vm.errors import err_at_offset, format_str
from vm import signature_token_help
from vm import SerializedType, Opcodes
from vm.file_format import (
        Bytecode, CompiledModule, FieldDefinitionIndex, FunctionDefinition, Kind, LocalIndex,
        LocalsSignatureIndex, SignatureToken, StructDefinitionIndex, ModuleAccess
    )
from vm.views import (
        FunctionDefinitionView, FunctionSignatureView, LocalsSignatureView, ModuleView,
        SignatureTokenView, StructDefinitionView, ViewInternals,
    )
from typing import List, Any, Optional, Mapping, Set, Union
from dataclasses import dataclass
from copy import deepcopy
from enum import IntEnum
from libra.rustlib import assert_true, bail, usize, flatten

checked_verify = assert_true


# This module defines the transfer functions for verifying type and memory safety of a
# procedure body.


@dataclass
class TypeAndMemorySafetyAnalysis(AbstractInterpreter):
    module_view: ModuleView
    function_definition_view: FunctionDefinitionView
    locals_signature_view: LocalsSignatureView
    stack: List[TypedAbstractValue]

    @classmethod
    def verify(cls,
        module: CompiledModule,
        function_definition: FunctionDefinition,
        cfg: VMControlFlowGraph,
    ) -> List[VMStatus]:
        function_definition_view = FunctionDefinitionView.new(module, function_definition)
        locals_signature_view = function_definition_view.locals_signature()
        function_signature_view = function_definition_view.signature()
        if function_signature_view.arg_count() > locals_signature_view.__len__():
            return [VMStatus(StatusCode.RANGE_OUT_OF_BOUNDS).with_message(
                "Fewer locals than parameters")]

        def lambda0(arg_idx, arg_type_view):
            arg_token = arg_type_view.as_inner()
            local_token = locals_signature_view.token_at(arg_idx).as_inner()
            if arg_token == local_token:
                return []
            else:
                return [
                    VMStatus(StatusCode.TYPE_MISMATCH).with_message(format_str(
                        "Type mismatch at index {} between parameter and local",
                        arg_idx
                    )),
                ]

        errors: List[VMStatus] = [lambda0(idx, view) for (idx, view) in \
            enumerate(function_signature_view.arg_tokens())]

        errors = flatten(errors)
        if errors:
            return errors

        initial_state =\
            AbstractState.new(FunctionDefinitionView.new(module, function_definition))
        verifier = TypeAndMemorySafetyAnalysis(
            ModuleView.new(module),
            FunctionDefinitionView.new(module, function_definition),
            locals_signature_view,
            [],
        )

        errors = []
        inv_map = verifier.analyze_function(initial_state, function_definition_view, cfg)
        # Report all the join failures
        for (block_id, inv) in inv_map.items():
            pre = inv.pre
            post = inv.post
            if inv.pre.tag == BlockPrecondition.JOIN_FAILURE:
                errors.append(err_at_offset(StatusCode.JOIN_FAILURE, block_id))

            if inv.post.tag == BlockPostcondition.ERROR:
                err = inv.post.error
                assert len(err) > 0
                errors.append(err)

        return errors


    def module(self) -> CompiledModule:
        return self.module_view.as_inner()


    # Gives the current constraints on the type formals in the current function.
    def type_formals(self) -> List[Kind]:
        return self\
            .function_definition_view\
            .signature()\
            .as_inner()\
            .type_formals

    @classmethod
    def is_readable_reference(cls,
        state: AbstractState,
        signature: SignatureToken,
        rid: RefID
    ) -> bool:
        checked_verify(signature.is_reference())
        return not signature.is_mutable_reference() or state.is_freezable(rid)


    # helper for both `ImmBorrowField` and `MutBorrowField`
    def borrow_field(
        self,
        errors: List[VMStatus],
        state: AbstractState,
        offset: usize,
        mut_: bool,
        field_definition_index: FieldDefinitionIndex,
    ):
        operand = self.stack.pop()
        struct_handle_index =\
            SignatureToken.get_struct_handle_from_reference(operand.signature)
        if struct_handle_index is None:
            errors.append(err_at_offset(
                StatusCode.BORROWFIELD_TYPE_MISMATCH_ERROR,
                offset,
            ))
            return

        if not self.module()\
            .is_field_in_struct(field_definition_index, struct_handle_index):
            errors.append(err_at_offset(
                StatusCode.BORROWFIELD_BAD_FIELD_ERROR,
                offset,
            ))
            return

        if mut_ and not operand.signature.is_mutable_reference():
            errors.append(err_at_offset(
                StatusCode.BORROWFIELD_TYPE_MISMATCH_ERROR,
                offset,
            ))
            return

        fid = state.borrow_field(operand, mut_, field_definition_index)
        if fid is not None:
            field_signature = deepcopy(self\
                .module()\
                .get_field_signature(field_definition_index).v0)

            field_token = field_signature\
                    .substitute(operand.signature.get_type_actuals_from_reference())
            if mut_:
                signature = signature_token_help.MutableReference(field_token)
            else:
                signature = signature_token_help.Reference(field_token)

            self.stack.append(TypedAbstractValue(
                signature,
                AbstractValue.Reference(fid),
            ))
            operand_id = operand.value.extract_id()
            state.remove(operand_id)
        else:
            errors.append(err_at_offset(
                StatusCode.BORROWFIELD_EXISTS_MUTABLE_BORROW_ERROR,
                offset,
            ))



    # helper for both `ImmBorrowLoc` and `MutBorrowLoc`
    def borrow_loc(
        self,
        errors: List[VMStatus],
        state: AbstractState,
        offset: usize,
        mut_: bool,
        idx: LocalIndex,
    ):
        loc_signature = deepcopy(self.locals_signature_view.token_at(idx).as_inner())

        if loc_signature.is_reference():
            errors.append(err_at_offset(StatusCode.BORROWLOC_REFERENCE_ERROR, offset))
            return

        if not state.is_available(idx):
            errors.append(err_at_offset(
                StatusCode.BORROWLOC_UNAVAILABLE_ERROR,
                offset,
            ))
            return

        aid = state.borrow_local_value(mut_, idx)
        if aid is not None:
            if mut_:
                signature = signature_token_help.MutableReference(loc_signature)
            else:
                signature = signature_token_help.Reference(loc_signature)

            self.stack.append(TypedAbstractValue(
                signature,
                value= AbstractValue.Reference(aid),
            ))
        else:
            errors.append(err_at_offset(
                StatusCode.BORROWLOC_EXISTS_BORROW_ERROR,
                offset,
            ))


    def borrow_global(
        self,
        errors: List[VMStatus],
        state: AbstractState,
        offset: usize,
        mut_: bool,
        idx: StructDefinitionIndex,
        type_actuals_idx: LocalsSignatureIndex,
    ):
        struct_definition = self.module().struct_def_at(idx)
        if not StructDefinitionView.new(self.module(), struct_definition).is_nominal_resource():
            errors.append(err_at_offset(
                StatusCode.BORROWGLOBAL_NO_RESOURCE_ERROR,
                offset,
            ))
            return

        type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
        struct_type =\
            signature_token_help.Struct(struct_definition.struct_handle, deepcopy(type_actuals))

        #TTODO: Maybe bug?
        SignatureTokenView.new(self.module(), struct_type).kind(self.type_formals())

        operand = self.stack.pop()
        if operand.signature.tag != SerializedType.ADDRESS:
            errors.append(err_at_offset(
                StatusCode.BORROWFIELD_TYPE_MISMATCH_ERROR,
                offset,
            ))
            return

        aid = state.borrow_global_value(mut_, idx)
        if aid is not None:
            if mut_:
                signature = signature_token_help.MutableReference(struct_type)
            else:
                signature = signature_token_help.Reference(struct_type)

            self.stack.append(TypedAbstractValue(
                signature,
                value= AbstractValue.Reference(aid),
            ))
        else:
            errors.append(err_at_offset(StatusCode.GLOBAL_REFERENCE_ERROR, offset))


    def execute_inner(
        self,
        errors: List[VMStatus],
        state: AbstractState,
        bytecode: Bytecode,
        offset: usize,
    ):
        tag = bytecode.tag
        if tag == Opcodes.POP:
            operand = self.stack.pop()
            kind = SignatureTokenView.new(self.module(), operand.signature)\
                .kind(self.type_formals())
            if kind != Kind.Unrestricted:
                errors.append(err_at_offset(StatusCode.POP_RESOURCE_ERROR, offset))
                return

            if operand.value.tag == AbstractValue.REFERENCE:
                state.remove(operand.value.value)

        elif tag == Opcodes.BR_TRUE or tag == Opcodes.BR_FALSE:
            operand = self.stack.pop()
            if operand.signature.tag != SerializedType.BOOL:
                errors.append(err_at_offset(StatusCode.BR_TYPE_MISMATCH_ERROR, offset))

        elif tag == Opcodes.ST_LOC:
            idx = bytecode.value
            operand = self.stack.pop()
            if operand.signature != self.locals_signature_view.token_at(idx).as_inner():
                errors.append(err_at_offset(StatusCode.STLOC_TYPE_MISMATCH_ERROR, offset))
                return

            if state.is_available(idx):
                if state.is_local_safe_to_destroy(idx):
                    state.destroy_local(idx)
                else:
                    errors.append(err_at_offset(
                        StatusCode.STLOC_UNSAFE_TO_DESTROY_ERROR,
                        offset,
                    ))
                    return

            state.insert_local(idx, operand)

        elif tag == Opcodes.ABORT:
            error_code = self.stack.pop()
            if error_code.signature != signature_token_help.U64:
                errors.append(err_at_offset(StatusCode.ABORT_TYPE_MISMATCH_ERROR, offset))
                return

            state.replace_with(AbstractState.default())

        elif tag == Opcodes.RET:
            for idx in range(self.locals_signature_view.__len__()):
                local_idx = idx
                is_reference = state.is_available(local_idx)\
                    and state.local(local_idx).value.is_reference()
                if is_reference:
                    state.destroy_local(local_idx)

            if not state.is_frame_safe_to_destroy():
                errors.append(err_at_offset(
                    StatusCode.RET_UNSAFE_TO_DESTROY_ERROR,
                    offset,
                ))
                return

            for return_type_view in reversed(self\
                .function_definition_view\
                .signature()\
                .return_tokens()):
                operand = self.stack.pop()
                if operand.signature != return_type_view.as_inner():
                    errors.append(err_at_offset(StatusCode.RET_TYPE_MISMATCH_ERROR, offset))
                    return

                if return_type_view.is_mutable_reference():
                    if operand.value.tag == AbstractValue.REFERENCE:
                        if state.is_borrowed(operand.value.value):
                            errors.append(err_at_offset(
                                StatusCode.RET_BORROWED_MUTABLE_REFERENCE_ERROR,
                                offset,
                            ))
                            return

            state.replace_with(AbstractState.default())


        elif tag == Opcodes.BRANCH:
            pass

        elif tag == Opcodes.FREEZE_REF:
            operand = self.stack.pop()
            if operand.signature.tag == SerializedType.MUTABLE_REFERENCE:
                signature = operand.signature.reference
                operand_id = operand.value.extract_id()
                if state.is_freezable(operand_id):
                    self.stack.append(TypedAbstractValue(
                        signature= signature_token_help.Reference(signature),
                        value= operand.value,
                    ))
                else:
                    errors.append(err_at_offset(
                        StatusCode.FREEZEREF_EXISTS_MUTABLE_BORROW_ERROR,
                        offset,
                    ))

            else:
                errors.append(err_at_offset(
                    StatusCode.FREEZEREF_TYPE_MISMATCH_ERROR,
                    offset,
                ))

        elif tag == Opcodes.MUT_BORROW_FIELD:
            field_definition_index = bytecode.value
            self.borrow_field(errors, state, offset, True, field_definition_index)
        elif tag == Opcodes.IMM_BORROW_FIELD:
            field_definition_index = bytecode.value
            self.borrow_field(errors, state, offset, False, field_definition_index)

        elif tag == Opcodes.LD_U8:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.U8,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.LD_U64:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.U64,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.LD_U128:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.U128,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.LD_ADDR:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.ADDRESS,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.LD_BYTEARRAY:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.VectorU8,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.LD_TRUE or tag == Opcodes.LD_FALSE:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.BOOL,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.COPY_LOC:
            idx = bytecode.value
            signature_view = self.locals_signature_view.token_at(idx)
            if not state.is_available(idx):
                errors.append(err_at_offset(StatusCode.COPYLOC_UNAVAILABLE_ERROR, offset))
            elif signature_view.is_reference():
                rid = state.borrow_local_reference(idx)
                self.stack.append(TypedAbstractValue(
                    signature= deepcopy(signature_view.as_inner()),
                    value= AbstractValue.Reference(rid),
                ))
            else:
                kind = signature_view.kind(self.type_formals())
                if kind == Kind.Resource or kind == Kind.All:
                    errors.append(err_at_offset(StatusCode.COPYLOC_RESOURCE_ERROR, offset))
                elif kind == Kind.Unrestricted:
                    if not state.is_local_mutably_borrowed(idx):
                        self.stack.append(TypedAbstractValue(
                            signature= deepcopy(signature_view.as_inner()),
                            value= AbstractValue.Value(Kind.Unrestricted),
                        ))
                    else:
                        errors.append(err_at_offset(
                            StatusCode.COPYLOC_EXISTS_BORROW_ERROR,
                            offset,
                        ))

        elif tag == Opcodes.MOVE_LOC:
            idx = bytecode.value
            signature = deepcopy(self.locals_signature_view.token_at(idx).as_inner())
            if not state.is_available(idx):
                errors.append(err_at_offset(StatusCode.MOVELOC_UNAVAILABLE_ERROR, offset))
            elif signature.is_reference() or not state.is_local_borrowed(idx):
                value = state.remove_local(idx)
                self.stack.append(value)
            else:
                errors.append(err_at_offset(
                    StatusCode.MOVELOC_EXISTS_BORROW_ERROR,
                    offset,
                ))

        elif tag == Opcodes.MUT_BORROW_LOC:
            self.borrow_loc(errors, state, offset, True, bytecode.value)

        elif tag == Opcodes.IMM_BORROW_LOC:
            self.borrow_loc(errors, state, offset, False, bytecode.value)

        elif tag == Opcodes.CALL:
            (idx, type_actuals_idx) = bytecode.value
            function_handle = self.module().function_handle_at(idx)
            function_signature = self.module()\
                .function_signature_at(function_handle.signature)

            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            function_acquired_resources = self.module_view\
                .function_acquired_resources(function_handle)

            for acquired_resource in function_acquired_resources:
                if state.is_global_borrowed(acquired_resource):
                    errors.append(err_at_offset(StatusCode.GLOBAL_REFERENCE_ERROR, offset))
                    return

            function_signature_view =\
                FunctionSignatureView.new(self.module(), function_signature)
            all_references_to_borrow_from = set() #BTreeSet.new()
            mutable_references_to_borrow_from = set() #BTreeSet.new()

            for arg_type in reversed(function_signature.arg_types):
                arg = self.stack.pop()
                if arg.signature != arg_type.substitute(type_actuals):
                    errors.append(err_at_offset(StatusCode.CALL_TYPE_MISMATCH_ERROR, offset))
                    return

                if arg.value.tag == AbstractValue.REFERENCE:
                    aid = arg.value.value
                    if arg_type.is_mutable_reference():
                        if state.is_borrowed(aid):
                            errors.append(err_at_offset(
                                StatusCode.CALL_BORROWED_MUTABLE_REFERENCE_ERROR,
                                offset,
                            ))
                            return

                        mutable_references_to_borrow_from.add(aid)
                    all_references_to_borrow_from.add(aid)

            for return_type_view in function_signature_view.return_tokens():
                if return_type_view.is_reference():
                    if return_type_view.is_mutable_reference():
                        rid = state.borrow_from(mutable_references_to_borrow_from)
                    else:
                        rid = state.borrow_from(all_references_to_borrow_from)

                    self.stack.append(TypedAbstractValue(
                        signature= return_type_view.as_inner().substitute(type_actuals),
                        value= AbstractValue.Reference(rid),
                    ))
                else:
                    return_type = return_type_view.as_inner().substitute(type_actuals)
                    kind = SignatureTokenView.new(self.module(), return_type)\
                        .kind(self.type_formals())
                    self.stack.append(TypedAbstractValue(
                        signature= return_type,
                        value= AbstractValue.Value(kind),
                    ))

            for aid in all_references_to_borrow_from:
                state.remove(aid)


        elif tag == Opcodes.PACK:
            (idx, type_actuals_idx) = bytecode.value
            # Build and verify the class type.
            struct_definition = self.module().struct_def_at(idx)
            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            struct_type = signature_token_help.Struct(
                struct_definition.struct_handle, deepcopy(type_actuals))
            kind = SignatureTokenView.new(
                self.module(), struct_type).kind(self.type_formals())

            struct_definition_view =\
                StructDefinitionView.new(self.module(), struct_definition)

            fields = struct_definition_view.fields()
            if fields is None:
                # TODO pack on native error
                errors.append(err_at_offset(StatusCode.PACK_TYPE_MISMATCH_ERROR, offset))
            else:
                for field_definition_view in reversed(fields):
                    field_signature_view = field_definition_view.type_signature()
                    # Substitute type variables with actual types.
                    field_type = field_signature_view.token().as_inner()\
                        .substitute(type_actuals)
                    # TODO: is it necessary to verify kind constraints here
                    arg = self.stack.pop()
                    if arg.signature != field_type:
                        errors.append(err_at_offset(
                            StatusCode.PACK_TYPE_MISMATCH_ERROR,
                            offset,
                        ))

            self.stack.append(TypedAbstractValue(
                signature= struct_type,
                value= AbstractValue.Value(kind),
            ))

        elif tag == Opcodes.UNPACK:
            (idx, type_actuals_idx) = bytecode.value
            # Build and verify the class type.
            struct_definition = self.module().struct_def_at(idx)
            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            struct_type = signature_token_help.Struct(
                struct_definition.struct_handle, deepcopy(type_actuals))

            # Pop an abstract value from the stack and check if its type is equal to the one
            # declared. TODO: is it safe to not call verify the kinds if the types are equal
            arg = self.stack.pop()
            if arg.signature != struct_type:
                errors.append(err_at_offset(
                    StatusCode.UNPACK_TYPE_MISMATCH_ERROR,
                    offset,
                ))
                return

            # For each field, push an abstract value to the stack.
            struct_definition_view =\
                StructDefinitionView.new(self.module(), struct_definition)
            fields = struct_definition_view.fields()
            if fields is None:
                # TODO unpack on native error
                errors.append(err_at_offset(
                    StatusCode.UNPACK_TYPE_MISMATCH_ERROR,
                    offset,
                ))
            else:
                for field_definition_view in fields:
                    field_signature_view = field_definition_view.type_signature()
                    # Substitute type variables with actual types.
                    field_type = field_signature_view.token().as_inner()\
                        .substitute(type_actuals)
                    # Get the kind of the type.
                    kind = SignatureTokenView.new(self.module(), field_type)\
                        .kind(self.type_formals())
                    self.stack.append(TypedAbstractValue(
                        signature= field_type,
                        value= AbstractValue.Value(kind),
                    ))

        elif tag == Opcodes.READ_REF:
            tav = self.stack.pop()
            operand_signature = tav.signature
            operand_value = tav.value
            if not operand_signature.is_reference():
                errors.append(err_at_offset(
                    StatusCode.READREF_TYPE_MISMATCH_ERROR,
                    offset,
                ))
                return

            operand_id = operand_value.extract_id()
            if not self.__class__.is_readable_reference(state, operand_signature, operand_id):
                errors.append(err_at_offset(
                    StatusCode.READREF_EXISTS_MUTABLE_BORROW_ERROR,
                    offset,
                ))
            else:
                if operand_signature.tag in [
                    SerializedType.REFERENCE,
                    SerializedType.MUTABLE_REFERENCE,
                ]:
                    inner_signature = operand_signature.reference
                else:
                    bail("Unreachable")

                if SignatureTokenView.new(self.module(), inner_signature)\
                    .kind(self.type_formals()) != Kind.Unrestricted:
                    errors.append(err_at_offset(StatusCode.READREF_RESOURCE_ERROR, offset))
                else:
                    self.stack.append(TypedAbstractValue(
                        signature= inner_signature,
                        value= AbstractValue.Value(Kind.Unrestricted),
                    ))
                    state.remove(operand_id)

        elif tag == Opcodes.WRITE_REF:
            ref_operand = self.stack.pop()
            val_operand = self.stack.pop()
            if ref_operand.signature.tag == SerializedType.MUTABLE_REFERENCE:
                signature = ref_operand.signature.reference
                kind = SignatureTokenView.new(self.module(), signature)\
                    .kind(self.type_formals())
                if kind == Kind.Resource or kind == Kind.All:
                    errors.append(err_at_offset(StatusCode.WRITEREF_RESOURCE_ERROR, offset))
                elif kind == Kind.Unrestricted:
                    if val_operand.signature != signature:
                        errors.append(err_at_offset(
                            StatusCode.WRITEREF_TYPE_MISMATCH_ERROR,
                            offset,
                        ))
                    else:
                        ref_operand_id = ref_operand.value.extract_id()
                        if not state.is_borrowed(ref_operand_id):
                            state.remove(ref_operand_id)
                        else:
                            errors.append(err_at_offset(
                                StatusCode.WRITEREF_EXISTS_BORROW_ERROR,
                                offset,
                            ))
                else:
                    bail("Unreachable")
            else:
                errors.append(err_at_offset(
                    StatusCode.WRITEREF_NO_MUTABLE_REFERENCE_ERROR,
                    offset,
                ))


        elif tag == Opcodes.CAST_U8:
            operand = self.stack.pop()
            if operand.signature.is_integer():
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.U8,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))

        elif tag == Opcodes.CAST_U64:
            operand = self.stack.pop()
            if operand.signature.is_integer():
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.U64,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.CAST_U128:
            operand = self.stack.pop()
            if operand.signature.is_integer():
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.U128,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))

        elif tag in [
            Opcodes.ADD,
            Opcodes.SUB,
            Opcodes.MUL,
            Opcodes.MOD,
            Opcodes.DIV,
            Opcodes.BIT_OR,
            Opcodes.BIT_AND,
            Opcodes.XOR,
        ]:
            operand1 = self.stack.pop()
            operand2 = self.stack.pop()
            if operand1.signature.is_integer() and operand1.signature == operand2.signature:
                self.stack.append(TypedAbstractValue(
                    signature= operand1.signature,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag in [
            Opcodes.SHL,
            Opcodes.SHR,
        ]:
            operand1 = self.stack.pop()
            operand2 = self.stack.pop()
            if operand2.signature.is_integer() and operand1.signature == signature_token_help.U8:
                self.stack.append(TypedAbstractValue(
                    signature= operand2.signature,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag in [
            Opcodes.OR,
            Opcodes.AND,
        ]:
            operand1 = self.stack.pop()
            operand2 = self.stack.pop()
            if operand1.signature == signature_token_help.BOOL\
                and operand2.signature == signature_token_help.BOOL:
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.BOOL,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.BOOLEAN_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.NOT:
            operand = self.stack.pop()
            if operand.signature == signature_token_help.BOOL:
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.BOOL,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.BOOLEAN_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.EQ or tag == Opcodes.NEQ:
            operand1 = self.stack.pop()
            operand2 = self.stack.pop()
            kind1 = SignatureTokenView.new(self.module(), operand1.signature)\
                .kind(self.type_formals())
            is_copyable = kind1 == Kind.Unrestricted
            if is_copyable and operand1.signature == operand2.signature:
                if operand1.value.tag == AbstractValue.REFERENCE:
                    rid = operand1.value.value
                    if self.__class__.is_readable_reference(state, operand1.signature, rid):
                        state.remove(rid)
                    else:
                        errors.append(err_at_offset(
                            StatusCode.READREF_EXISTS_MUTABLE_BORROW_ERROR,
                            offset,
                        ))
                        return

                if operand2.value.tag == AbstractValue.REFERENCE:
                    rid = operand2.value.value
                    if self.__class__.is_readable_reference(state, operand2.signature, rid):
                        state.remove(rid)
                    else:
                        errors.append(err_at_offset(
                            StatusCode.READREF_EXISTS_MUTABLE_BORROW_ERROR,
                            offset,
                        ))
                        return

                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.BOOL,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.EQUALITY_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag in [
            Opcodes.LT,
            Opcodes.GT,
            Opcodes.LE,
            Opcodes.GE,
        ]:
            operand1 = self.stack.pop()
            operand2 = self.stack.pop()
            if operand1.signature.is_integer() and operand1.signature == operand2.signature:
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.BOOL,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.INTEGER_OP_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.EXISTS:
            (idx, type_actuals_idx) = bytecode.value
            struct_definition = self.module().struct_def_at(idx)
            if not StructDefinitionView.new(self.module(), struct_definition).is_nominal_resource():
                errors.append(err_at_offset(
                    StatusCode.EXISTS_RESOURCE_TYPE_MISMATCH_ERROR,
                    offset,
                ))
                return

            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            struct_type =signature_token_help.Struct(
                struct_definition.struct_handle, deepcopy(type_actuals))

            #TTODO
            SignatureTokenView.new(self.module(), struct_type).kind(self.type_formals())

            operand = self.stack.pop()
            if operand.signature == signature_token_help.ADDRESS:
                self.stack.append(TypedAbstractValue(
                    signature= signature_token_help.BOOL,
                    value= AbstractValue.Value(Kind.Unrestricted),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.EXISTS_RESOURCE_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.MUT_BORROW_GLOBAL:
            (idx, type_actuals_idx) = bytecode.value
            self.borrow_global(errors, state, offset, True, idx, type_actuals_idx)

        elif tag == Opcodes.IMM_BORROW_GLOBAL:
            (idx, type_actuals_idx) = bytecode.value
            self.borrow_global(errors, state, offset, False, idx, type_actuals_idx)


        elif tag == Opcodes.MOVE_FROM:
            (idx, type_actuals_idx) = bytecode.value
            struct_definition = self.module().struct_def_at(idx)
            if not StructDefinitionView.new(self.module(), struct_definition).is_nominal_resource():
                errors.append(err_at_offset(
                    StatusCode.MOVEFROM_NO_RESOURCE_ERROR,
                    offset,
                ))
                return
            elif state.is_global_borrowed(idx):
                errors.append(err_at_offset(StatusCode.GLOBAL_REFERENCE_ERROR, offset))
                return

            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            struct_type = signature_token_help.Struct(
                struct_definition.struct_handle, deepcopy(type_actuals))

            #TTODO
            SignatureTokenView.new(self.module(), struct_type).kind(self.type_formals())

            operand = self.stack.pop()
            if operand.signature == signature_token_help.ADDRESS:
                self.stack.append(TypedAbstractValue(
                    signature= struct_type,
                    value= AbstractValue.Value(Kind.Resource),
                ))
            else:
                errors.append(err_at_offset(
                    StatusCode.MOVEFROM_TYPE_MISMATCH_ERROR,
                    offset,
                ))


        elif tag == Opcodes.MOVE_TO:
            (idx, type_actuals_idx) = bytecode.value
            struct_definition = self.module().struct_def_at(idx)
            if not StructDefinitionView.new(self.module(), struct_definition).is_nominal_resource():
                errors.append(err_at_offset(
                    StatusCode.MOVETOSENDER_NO_RESOURCE_ERROR,
                    offset,
                ))
                return

            type_actuals = self.module().locals_signature_at(type_actuals_idx).v0
            struct_type =signature_token_help.Struct(
                struct_definition.struct_handle, deepcopy(type_actuals))
            #TTODO
            SignatureTokenView.new(self.module(), struct_type).kind(self.type_formals())

            value_operand = self.stack.pop()
            if value_operand.signature != struct_type:
                errors.append(err_at_offset(
                    StatusCode.MOVETOSENDER_TYPE_MISMATCH_ERROR,
                    offset,
                ))

        elif tag in [
            Opcodes.GET_TXN_GAS_UNIT_PRICE,
            Opcodes.GET_TXN_MAX_GAS_UNITS,
            Opcodes.GET_GAS_REMAINING,
            Opcodes.GET_TXN_SEQUENCE_NUMBER,
        ]:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.U64,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.GET_TXN_SENDER:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.ADDRESS,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))

        elif tag == Opcodes.GET_TXN_PUBLIC_KEY:
            self.stack.append(TypedAbstractValue(
                signature= signature_token_help.VectorU8,
                value= AbstractValue.Value(Kind.Unrestricted),
            ))
        else:
            bail("Unreachable!")


# impl<'a> TransferFunctions for TypeAndMemorySafetyAnalysis<'a> {
#     type State = AbstractState
#     type AnalysisError = List[VMStatus]

    def execute(
        self,
        state: AbstractState,
        bytecode: Bytecode,
        index: usize,
        last_index: usize,
    ) -> List[VMStatus]:
        errors = []
        self.execute_inner(errors, state, bytecode, index)
        if not errors:
            if index == last_index:
                state.replace_with(state.construct_canonical_state())
            return []
        else:
            return errors

