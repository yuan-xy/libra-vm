from __future__ import annotations
from typing import List, Set, Mapping, Iterable, Optional, Tuple
from dataclasses import dataclass
import abc
from libra.rustlib import flatten
from libra.vm_error import StatusCode, VMStatus
from libra_vm import IndexKind, Opcodes, SerializedNativeStructFlag, SerializedType
from libra_vm.errors import append_err_info
from libra_vm.file_format import (
        Bytecode, CompiledModule, Kind, SignatureToken, StructFieldInformation, StructHandle,
        TypeSignature,
    )


# This module implements a checker for verifying signature tokens used in types of function
# parameters, locals, and fields of structs are well-formed. References can only occur at the
# top-level in all tokens.  Additionally, references cannot occur at all in field types.

@dataclass
class SignatureChecker:
    module: CompiledModule


    def verify(self) -> List[VMStatus]:
        return flatten([
            self.verify_function_signatures(),
            self.verify_fields(),
            self.verify_code_units(),
        ])
        # self.legacy_verify_type_signatures()

    # This is a hack to satisfy the existing prop tests.
    # TODO: Remove it once we rework prop tests.
    # def legacy_verify_type_signatures(self) -> List[VMStatus]
    #     use SignatureToken.*

    #     self.module
    #         .type_signatures()
    #         .iter()
    #         .filter_map(|TypeSignature(ty)| match ty {
    #             Reference(inner) | MutableReference(inner) => match **inner {
    #                 Reference(_) | MutableReference(_) => {
    #                     Some(VMStatus(StatusCode.INVALID_SIGNATURE_TOKEN))
    #                 }
    #                 _ => None,
    #             },
    #             _ => None,
    #         })
    # }

    def verify_function_signatures(self) -> List[VMStatus]:
        ret = []
        for (idx, sig) in enumerate(self.module.function_signatures()):
            context = (self.module.struct_handles(), sig.type_formals)
            errors_return_types = []
            for ty in sig.return_types:
                errors = check_signature(context, ty)
                for err in errors:
                    append_err_info(err, IndexKind.FunctionSignature, idx)
                errors_return_types.append(errors)

            errors_arg_types = []
            for ty in sig.arg_types:
                errors = check_signature(context, ty)
                for err in errors:
                    append_err_info(err, IndexKind.FunctionSignature, idx)
                errors_arg_types.append(errors)

            ret.extend(errors_return_types)
            ret.extend(errors_arg_types)
        return flatten(ret)



    def verify_fields(self) -> List[VMStatus]:
        ret = []
        for (struct_def_idx, struct_def) in enumerate(self.module.struct_defs()):
            if struct_def.field_information.tag == SerializedNativeStructFlag.DECLARED:
                field_count = struct_def.field_information.field_count
                fields = struct_def.field_information.fields
                struct_handle = self.module.struct_handle_at(struct_def.struct_handle)
                start = fields.v0
                end = start + (field_count)
                context = (
                    self.module.struct_handles(),
                    struct_handle.type_formals,
                )

                for (field_def_idx, field_def) in enumerate(self.module.field_defs()[start:end]):
                    ty = self.module.type_signature_at(field_def.signature)

                    for err in check_signature_no_refs(context, ty.v0):
                        append_err_info(
                            append_err_info(
                                append_err_info(
                                    VMStatus(StatusCode.INVALID_FIELD_DEF).append(err),
                                    IndexKind.TypeSignature,
                                    field_def.signature.v0,
                                ),
                                IndexKind.FieldDefinition,
                                field_def_idx,
                            ),
                            IndexKind.StructDefinition,
                            struct_def_idx,
                        )
                        ret.append(err)
        return ret


    def verify_code_units(self) -> List[VMStatus]:
        ret = []
        for (func_def_idx, func_def) in enumerate(self.module.function_defs()):
            # Nothing to check for native functions so skipping.
            if func_def.is_native():
                continue
            else:
                # Check if the types of the locals are well defined.
                func_handle = self.module.function_handle_at(func_def.function)
                func_sig = self.module.function_signature_at(func_handle.signature)
                context = (
                    self.module.struct_handles(),
                    func_sig.type_formals,
                )
                locals_idx = func_def.code.locals
                localss = self.module.locals_signature_at(locals_idx).v0
                errors_locals = []
                for ty in localss:
                    errors = check_signature(context, ty)
                    for err in errors:
                        append_err_info(
                            append_err_info(err, IndexKind.LocalsSignature, locals_idx.v0),
                            IndexKind.FunctionDefinition,
                            func_def_idx,
                        )
                    errors_locals.extend(errors)


                # Check if the type actuals in certain bytecode instructions are well defined.
                errors_bytecodes = []
                for (offset, instr) in enumerate(func_def.code.code):
                    if instr.tag == Opcodes.CALL:
                        (idx, type_actuals_idx) = instr.value
                        func_handle = self.module.function_handle_at(idx)
                        func_sig =\
                            self.module.function_signature_at(func_handle.signature)
                        type_actuals =\
                            self.module.locals_signature_at(*type_actuals_idx).v0
                        errors = check_generic_instance(
                            context,
                            func_sig.type_formals,
                            type_actuals,
                        )
                    elif instr.tag == Opcodes.PACK or instr.tag == Opcodes.UNPACK:
                        (idx, type_actuals_idx) = instr.value
                        struct_def = self.module.struct_def_at(idx)
                        struct_handle =\
                            self.module.struct_handle_at(struct_def.struct_handle)
                        type_actuals =\
                            self.module.locals_signature_at(type_actuals_idx).v0
                        errors = check_generic_instance(
                            context,
                            struct_handle.type_formals,
                            type_actuals,
                        )
                    elif instr.tag in [
                        Opcodes.EXISTS,
                        Opcodes.MOVE_FROM,
                        Opcodes.MOVE_TO,
                        Opcodes.IMM_BORROW_GLOBAL,
                        Opcodes.MUT_BORROW_GLOBAL,
                    ]:
                        (idx, type_actuals_idx) = instr.value
                        struct_def = self.module.struct_def_at(idx)
                        struct_handle =\
                            self.module.struct_handle_at(struct_def.struct_handle)
                        type_actuals =\
                            self.module.locals_signature_at(type_actuals_idx).v0
                        errors = check_generic_instance(
                            context,
                            struct_handle.type_formals,
                            type_actuals,
                        )
                    else:
                        errors = []

                    for err in errors:
                        append_err_info(
                            err.append_message_with_separator(
                                ' ',
                                format_str("at offset {} ", offset),
                            ),
                            IndexKind.FunctionDefinition,
                            func_def_idx,
                        )

                    errors_bytecodes.extend(errors)


                ret.extend(errors_locals)
                ret.extend(errors_bytecodes)
        return flatten(ret)



# Checks if the given types are well defined and satisfy the given kind constraints in the given
# context.
def check_generic_instance(
    context: Tuple[List[StructHandle], List[Kind]],
    constraints: List[Kind],
    type_actuals: List[SignatureToken],
) -> List[VMStatus]:
    breakpoint()
    errors = [check_signature_no_refs(context, ty) for ty in type_actuals]

    if constraints.__len__() != type_actuals.__len__():
        errors.append(
            VMStatus(StatusCode.NUMBER_OF_TYPE_ACTUALS_MISMATCH).with_message(format_str(
                "expected {} type actuals got {}",
                constraints.__len__(),
                type_actuals.__len__()
            )),
        )
        return flatten(errors)


    kinds = [SignatureToken.kind(context, ty) for ty in type_actuals]

    for (c, k, ty) in zip(constraints, kinds, type_actuals):
        if not k.is_sub_kind_of(c):
            errors.append(
                VMStatus(StatusCode.CONTRAINT_KIND_MISMATCH).with_message(format_str(
                    "expected kind {} got type actual {} with incompatible kind {}",
                    c, ty, k
                )),
            )
    return errors


# Checks if the given type is well defined in the given context. No references are permitted.
def check_signature_no_refs(
    context: Tuple[List[StructHandle], List[Kind]],
    ty: SignatureToken,
) -> List[VMStatus]:

    (struct_handles, _) = context

    if ty.tag == SerializedType.REFERENCE or ty.tag == SerializedType.MUTABLE_REFERENCE:
        # TODO: Prop tests expect us to NOT check the inner types.
        # Revisit this once we rework prop tests.
        return [VMStatus(StatusCode.INVALID_SIGNATURE_TOKEN)\
            .with_message("reference not allowed")]

    elif ty.tag == SerializedType.VECTOR:
        return check_signature_no_refs(context, ty)

    elif ty.tag == SerializedType.STRUCT:
        sh = struct_handles[idx.v0]
        return check_generic_instance(context, sh.type_formals, type_actuals)
    else:
        return []


# Checks if the given type is well defined in the given context. References are only permitted
# at the top level.
def check_signature(context: Tuple[List[StructHandle], List[Kind]], ty: SignatureToken) -> List[VMStatus]:
    if ty.tag == SerializedType.REFERENCE or ty.tag == SerializedType.MUTABLE_REFERENCE:
        inner = ty.reference
        return check_signature_no_refs(context, inner)
    else:
        return check_signature_no_refs(context, ty)

