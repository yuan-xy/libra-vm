from libra_vm.errors import append_err_info, bounds_error, bytecode_offset_err, verification_error
from libra_vm.file_format import (
    Bytecode, CodeUnit, CompiledModuleMut, FieldDefinition, FunctionDefinition, FunctionHandle,
    FunctionSignature, Kind, LocalsSignature, LocalsSignatureIndex, ModuleHandle,
    SignatureToken, StructDefinition, StructFieldInformation, StructHandle, TypeSignature
)
from libra_vm.file_format_common import *
from libra_vm.internals import ModuleIndex
from libra_vm.lib import IndexKind
from libra.vm_error import StatusCode, VMStatus
from dataclasses import dataclass
from typing import List, Optional, Tuple, Iterable, Any
from libra.rustlib import usize, flatten


@dataclass
class BoundsChecker:
    module: CompiledModuleMut

    def verify(self) -> List[VMStatus]:
        errors = []

        # A module (or script) must always have at least one module handle. (For modules the first
        # handle should be the same as the sender -- the bytecode verifier is unaware of
        # transactions so it does not perform this check.
        if not self.module.module_handles:
            status = verification_error(IndexKind.ModuleHandle, 0, StatusCode.NO_MODULE_HANDLES)
            errors.append([status])

        errors.append(BoundsChecker.verify_pool(
            IndexKind.ModuleHandle,
            self.module.module_handles,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.StructHandle,
            self.module.struct_handles,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.FunctionHandle,
            self.module.function_handles,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.StructDefinition,
            self.module.struct_defs,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.FieldDefinition,
            self.module.field_defs,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.FunctionDefinition,
            self.module.function_defs,
            self.module,
        ))
        errors.append(BoundsChecker.verify_pool(
            IndexKind.FunctionSignature,
            self.module.function_signatures,
            self.module,
        ))

        # Check the class handle indices in locals signatures.
        # Type parameter indices are checked later in a separate pass.
        for idx, localss in enumerate(self.module.locals_signatures):
            errs = localss.check_struct_handles(self.module.struct_handles)
            for err in errs:
                append_err_info(err, IndexKind.LocalsSignature, idx)
            errors.extend(errs)

        # Check the class handle indices in type signatures.
        for idx, ty in enumerate(self.module.type_signatures):
            errs = ty.check_struct_handles(self.module.struct_handles)
            for err in errs:
                append_err_info(err, IndexKind.TypeSignature, idx)
            errors.extend(errs)

        errors = flatten(errors)
        if errors:
            return errors


        # Fields and function bodies need to be done once the rest of the module is validated.
        def lambda1(field_def):
            sh = self.module.struct_handles[field_def.struct_.v0]
            sig = self.module.type_signatures[field_def.signature.v0]
            return sig.check_type_parameters(sh.type_formals.__len__())

        errors_type_signatures = [lambda1(x) for x in self.module.field_defs]

        def lambda2(function_def):
            if function_def.is_native():
                return []
            else:
                fh = self.module.function_handles[function_def.function.v0]
                sig = self.module.function_signatures[fh.signature.v0]
                return function_def.code.check_bounds((self.module, sig))

        errors_code_units = [lambda2(x) for x in self.module.function_defs]

        return flatten([flatten(errors_type_signatures), flatten(errors_code_units)])

    @classmethod
    def verify_pool(cls,
        kind: IndexKind,
        it: Iterable,
        context: Any,
    ) -> List[VMStatus]:
        ret = []
        for (idx, elem) in enumerate(it):
            ss = elem.check_bounds(context)
            for err in ss:
                append_err_info(err, kind, idx)
            ret.extend(ss)
        return flatten(ret)

# pub trait BoundsCheck<Context: Copy> {
#     def check_bounds(self, context: Context) -> List[VMStatus]
# }

def check_bounds_impl(pool: List[Any], mid: ModuleIndex) -> Optional[VMStatus]:
    idx = mid.into_index()
    length = pool.__len__()
    if idx >= length:
        status = bounds_error(mid.KIND, idx, length, StatusCode.INDEX_OUT_OF_BOUNDS)
        return status
    else:
        return None


def check_code_unit_bounds_impl(pool: List[Any], bytecode_offset: usize, mid: ModuleIndex) -> List[VMStatus]:
    idx = mid.into_index()
    length = pool.__len__()
    if idx >= length:
        status = bytecode_offset_err(
            mid.KIND,
            idx,
            length,
            bytecode_offset,
            StatusCode.INDEX_OUT_OF_BOUNDS,
        )
        return [status]
    else:
        return []


def check_bounds_ModuleHandle(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [
        check_bounds_impl(module.address_pool, self.address),
        check_bounds_impl(module.identifiers, self.name),
    ]
    return flatten(arr)

ModuleHandle.check_bounds = check_bounds_ModuleHandle



def check_bounds_StructHandle(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [
        check_bounds_impl(module.module_handles, self.module),
        check_bounds_impl(module.identifiers, self.name),
    ]
    return flatten(arr)

StructHandle.check_bounds = check_bounds_StructHandle


def check_bounds_FunctionHandle(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [
        check_bounds_impl(module.module_handles, self.module),
        check_bounds_impl(module.identifiers, self.name),
        check_bounds_impl(module.function_signatures, self.signature),
    ]
    return flatten(arr)

FunctionHandle.check_bounds = check_bounds_FunctionHandle



def check_bounds_StructDefinition(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [check_bounds_impl(module.struct_handles, self.struct_handle)]
    if self.field_information.tag == SerializedNativeStructFlag.DECLARED:
        arr.append(module.check_field_range(
            self.field_information.field_count,
            self.field_information.fields,
        ))
    return flatten(arr)

StructDefinition.check_bounds = check_bounds_StructDefinition



def check_bounds_FieldDefinition(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [
            check_bounds_impl(module.struct_handles, self.struct_),
            check_bounds_impl(module.identifiers, self.name),
            check_bounds_impl(module.type_signatures, self.signature),
        ]
    return flatten(arr)

FieldDefinition.check_bounds = check_bounds_FieldDefinition



def check_bounds_FunctionDefinition(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [check_bounds_impl(module.function_handles, self.function)]
    if not self.is_native():
        arr.append(check_bounds_impl(module.locals_signatures, self.code.locals))
    for idx in self.acquires_global_resources:
        arr.append(check_bounds_impl(module.struct_defs, idx))
    return flatten(arr)

FunctionDefinition.check_bounds = check_bounds_FunctionDefinition



def check_bounds_TypeSignature(self, context: Any) -> List[VMStatus]:
    return self.v0.check_bounds(context)

TypeSignature.check_bounds = check_bounds_TypeSignature




def check_bounds_FunctionSignature(self, module: CompiledModuleMut) -> List[VMStatus]:
    arr = [token.check_bounds((module, self)) for token in self.return_types]
    arr.extend([token.check_bounds((module, self)) for token in self.arg_types])
    return flatten(arr)

FunctionSignature.check_bounds = check_bounds_FunctionSignature


def check_bounds_SignatureToken(self, context: Any) -> List[VMStatus]:
    if isinstance(context, tuple) and len(context) == 2:
        (v0, v1) = context
        if isinstance(v0, list) and isinstance(v1, int):
            return check_bounds1(self, context)
        if isinstance(v0, list) and isinstance(v1, list):
            return check_bounds2(self, context)
        if isinstance(v0, CompiledModuleMut) and isinstance(v1, FunctionSignature):
            return check_bounds3(self, context)
        if isinstance(v0, CompiledModuleMut) and isinstance(v1, StructHandle):
            return check_bounds4(self, context)
    bail(f"unsupport context:{context}")

def check_bounds1(self, context: Tuple[List[StructHandle], usize]) -> List[VMStatus]:
    errors = self.check_type_parameters(context[1])
    errors.extend(self.check_struct_handles(context[0]))
    return flatten(errors)

def check_bounds2(self, context: Tuple[List[StructHandle], List[Kind]]) -> List[VMStatus]:
    return self.check_bounds((context[0], context[1].__len__()))


def check_bounds3(self, context: Tuple[CompiledModuleMut, FunctionSignature]) -> List[VMStatus]:
    return self.check_bounds((
        context[0].struct_handles,
        context[1].type_formals,
    ))

def check_bounds4(self, context: Tuple[CompiledModuleMut, StructHandle]) -> List[VMStatus]:
    breakpoint()
    #TODO: this branch is never executed.
    self.check_bounds((
        context[0].struct_handles,
        context[1].type_formals,
    ))

SignatureToken.check_bounds = check_bounds_SignatureToken


def check_type_actuals_bounds(
    context: (CompiledModuleMut, FunctionSignature),
    bytecode_offset: usize,
    idx: LocalsSignatureIndex,
) -> List[VMStatus]:
    (module, function_sig) = context
    errs = check_code_unit_bounds_impl(module.locals_signatures, bytecode_offset, idx)
    if errs:
        return errs

    return module.locals_signatures[idx.v0].check_type_parameters(function_sig.type_formals.__len__())



def check_bounds_CodeUnit(self, context: Tuple[CompiledModuleMut, FunctionSignature]) -> List[VMStatus]:
    (module, _) = context

    lcls = module.locals_signatures[self.locals.v0]
    locals_len = lcls.v0.__len__()

    code = self.code
    code_len = code.__len__()
    ret = []
    for (bytecode_offset, bytecode) in enumerate(code):
        tag = bytecode.tag
        value = bytecode.value
        # Instructions that refer to other pools.
        if tag == Opcodes.LD_ADDR:
            ret.extend(check_code_unit_bounds_impl(module.address_pool, bytecode_offset, value))
        elif tag == Opcodes.LD_BYTEARRAY:
            ret.extend(check_code_unit_bounds_impl(module.byte_array_pool, bytecode_offset, value))
        elif tag == Opcodes.MUT_BORROW_FIELD or tag == Opcodes.IMM_BORROW_FIELD:
            ret.extend(check_code_unit_bounds_impl(module.field_defs, bytecode_offset, value))
        elif tag == Opcodes.CALL:
            (idx, type_actuals_idx) = value
            errors = check_code_unit_bounds_impl(module.function_handles, bytecode_offset, idx)
            ret.extend(errors)
            ret.extend(check_type_actuals_bounds(
                    context,
                    bytecode_offset,
                    type_actuals_idx,
                ))
        elif tag == Opcodes.PACK or\
                tag == Opcodes.UNPACK or\
                tag == Opcodes.EXISTS or\
                tag == Opcodes.MUT_BORROW_GLOBAL or\
                tag == Opcodes.IMM_BORROW_GLOBAL or\
                tag == Opcodes.MOVE_FROM or\
                tag == Opcodes.MOVE_TO:
            (idx, type_actuals_idx) = value
            errors = check_code_unit_bounds_impl(module.struct_defs, bytecode_offset, idx)
            ret.extend(errors)
            ret.extend(check_type_actuals_bounds(
                            context,
                            bytecode_offset,
                            type_actuals_idx,
                        ))
        # Instructions that refer to this code block.
        elif tag == Opcodes.BR_TRUE or\
                tag == Opcodes.BR_FALSE or\
                tag == Opcodes.BRANCH:
            offset = value
            if offset >= code_len:
                status = bytecode_offset_err(
                    IndexKind.CodeDefinition,
                    offset,
                    code_len,
                    bytecode_offset,
                    StatusCode.INDEX_OUT_OF_BOUNDS,
                )
                ret.append(status)
        # Instructions that refer to the locals.
        elif tag == Opcodes.COPY_LOC or\
                tag == Opcodes.MOVE_LOC or\
                tag == Opcodes.ST_LOC or\
                tag == Opcodes.MUT_BORROW_LOC or\
                tag == Opcodes.IMM_BORROW_LOC:
            idx = value
            if idx >= locals_len:
                status = bytecode_offset_err(
                    IndexKind.LocalPool,
                    idx,
                    locals_len,
                    bytecode_offset,
                    StatusCode.INDEX_OUT_OF_BOUNDS,
                )
                ret.append(status)
        elif tag in [Opcodes.FREEZE_REF, Opcodes.POP, Opcodes.RET, Opcodes.LD_U8, Opcodes.LD_U64, Opcodes.LD_U128, Opcodes.CAST_U8, Opcodes.CAST_U64, Opcodes.CAST_U128, Opcodes.LD_TRUE, Opcodes.LD_FALSE, Opcodes.READ_REF, Opcodes.WRITE_REF, Opcodes.ADD, Opcodes.SUB, Opcodes.MUL, Opcodes.MOD, Opcodes.DIV, Opcodes.BIT_OR, Opcodes.BIT_AND, Opcodes.XOR, Opcodes.SHL, Opcodes.SHR, Opcodes.OR, Opcodes.AND, Opcodes.NOT, Opcodes.EQ, Opcodes.NEQ, Opcodes.LT, Opcodes.GT, Opcodes.LE, Opcodes.GE, Opcodes.ABORT, Opcodes.GET_TXN_GAS_UNIT_PRICE, Opcodes.GET_TXN_MAX_GAS_UNITS, Opcodes.GET_GAS_REMAINING, Opcodes.GET_TXN_SENDER, Opcodes.GET_TXN_SEQUENCE_NUMBER, Opcodes.GET_TXN_PUBLIC_KEY]:
            pass
            # List out the other options explicitly so there's a compile error if a new
            # bytecode gets added.
        else:
            bail("unreachble!")
    return ret


CodeUnit.check_bounds = check_bounds_CodeUnit
