from libra_vm.errors import append_err_info, bounds_error, bytecode_offset_err, verification_error
from libra_vm.file_format import (
    Bytecode, CodeUnit, CompiledModuleMut, FieldDefinition, FunctionDefinition, FunctionHandle,
    FunctionSignature, Kind, LocalsSignature, LocalsSignatureIndex, ModuleHandle,
    SignatureToken, StructDefinition, StructFieldInformation, StructHandle, TypeSignature
)
from libra_vm.internals import ModuleIndex
from libra_vm.lib import IndexKind
from libra.vm_error import StatusCode, VMStatus
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class BoundsChecker:
    module: CompiledModuleMut

    def verify(self) -> List[VMStatus]:
        errors = []
        return errors
"""
        # A module (or script) must always have at least one module handle. (For modules the first
        # handle should be the same as the sender -- the bytecode verifier is unaware of
        # transactions so it does not perform this check.
        if self.module.module_handles.is_empty() {
            status =
                verification_error(IndexKind.ModuleHandle, 0, StatusCode.NO_MODULE_HANDLES)
            errors.push([status])
        }

        errors.push(Self.verify_pool(
            IndexKind.ModuleHandle,
            self.module.module_handles.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.StructHandle,
            self.module.struct_handles.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.FunctionHandle,
            self.module.function_handles.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.StructDefinition,
            self.module.struct_defs.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.FieldDefinition,
            self.module.field_defs.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.FunctionDefinition,
            self.module.function_defs.iter(),
            self.module,
        ))
        errors.push(Self.verify_pool(
            IndexKind.FunctionSignature,
            self.module.function_signatures.iter(),
            self.module,
        ))

        # Check the class handle indices in locals signatures.
        # Type parameter indices are checked later in a separate pass.
        errors.push(
            self.module
                .locals_signatures
                .iter()
                .enumerate()
                .flat_map(|(idx, locals)| {
                    locals
                        .check_struct_handles(self.module.struct_handles)
                        .into_iter()
                        .map(move |err| append_err_info(err, IndexKind.LocalsSignature, idx))
                })
                .collect(),
        )

        # Check the class handle indices in type signatures.
        errors.push(
            self.module
                .type_signatures
                .iter()
                .enumerate()
                .flat_map(|(idx, ty)| {
                    ty.check_struct_handles(self.module.struct_handles)
                        .into_iter()
                        .map(move |err| append_err_info(err, IndexKind.TypeSignature, idx))
                })
                .collect(),
        )

        errors: List[_] = errors.into_iter().flatten().collect()
        if !errors.is_empty() {
            return errors
        }

        # Fields and function bodies need to be done once the rest of the module is validated.
        errors_type_signatures = self.module.field_defs.iter().flat_map(|field_def| {
            sh = self.module.struct_handles[field_def.struct_.0 as usize]
            sig = self.module.type_signatures[field_def.signature.0 as usize]

            sig.check_type_parameters(sh.type_formals.__len__())
        })

        errors_code_units = self.module.function_defs.iter().flat_map(|function_def| {
            if function_def.is_native() {
                []
            else:
                fh = self.module.function_handles[function_def.function.0 as usize]
                sig = self.module.function_signatures[fh.signature.0 as usize]
                function_def.code.check_bounds((self.module, sig))
            }
        })

        errors_type_signatures.chain(errors_code_units).collect()
    }

    #[inline]
    def verify_pool<Context, Item: 'a>(
        kind: IndexKind,
        iter: impl Iterator<Item = &'a Item>,
        context: Context,
    ) -> List[VMStatus]
    where
        Context: Copy,
        Item: BoundsCheck<Context>,
    {
        iter.enumerate()
            .flat_map(move |(idx, elem)| {
                elem.check_bounds(context)
                    .into_iter()
                    .map(move |err| append_err_info(err, kind, idx))
            })
            .collect()
    }
}

pub trait BoundsCheck<Context: Copy> {
    def check_bounds(self, context: Context) -> List[VMStatus]
}

#[inline]
def check_bounds_impl<T, I>(pool: &[T], idx: I) -> Optional[VMStatus]
where
    I: ModuleIndex,
{
    idx = idx.into_index()
    len = pool.__len__()
    if idx >= len {
        status = bounds_error(I.KIND, idx, len, StatusCode.INDEX_OUT_OF_BOUNDS)
        Some(status)
    else:
        None
    }
}

#[inline]
def check_code_unit_bounds_impl<T, I>(pool: &[T], bytecode_offset: usize, idx: I) -> List[VMStatus]
where
    I: ModuleIndex,
{
    idx = idx.into_index()
    len = pool.__len__()
    if idx >= len {
        status = bytecode_offset_err(
            I.KIND,
            idx,
            len,
            bytecode_offset,
            StatusCode.INDEX_OUT_OF_BOUNDS,
        )
        [status]
    else:
        []
    }
}

impl BoundsCheck<&CompiledModuleMut> for ModuleHandle {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.address_pool, self.address),
            check_bounds_impl(&module.identifiers, self.name),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}

impl BoundsCheck<&CompiledModuleMut> for StructHandle {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.module_handles, self.module),
            check_bounds_impl(&module.identifiers, self.name),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}

impl BoundsCheck<&CompiledModuleMut> for FunctionHandle {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.module_handles, self.module),
            check_bounds_impl(&module.identifiers, self.name),
            check_bounds_impl(&module.function_signatures, self.signature),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}

impl BoundsCheck<&CompiledModuleMut> for StructDefinition {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.struct_handles, self.struct_handle),
            match self.field_information {
                StructFieldInformation.Native => None,
                StructFieldInformation.Declared {
                    field_count,
                    fields,
                } => module.check_field_range(*field_count, *fields),
            },
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}

impl BoundsCheck<&CompiledModuleMut> for FieldDefinition {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.struct_handles, self.struct_),
            check_bounds_impl(&module.identifiers, self.name),
            check_bounds_impl(&module.type_signatures, self.signature),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}

impl BoundsCheck<&CompiledModuleMut> for FunctionDefinition {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        [
            check_bounds_impl(&module.function_handles, self.function),
            if self.is_native() {
                None
            else:
                check_bounds_impl(&module.locals_signatures, self.code.locals)
            },
        ]
        .into_iter()
        .flatten()
        .chain(
            self.acquires_global_resources
                .iter()
                .flat_map(|idx| check_bounds_impl(&module.struct_defs, *idx)),
        )
        .collect()
    }
}

impl<Context> BoundsCheck<Context> for TypeSignature
where
    Context: Copy,
    SignatureToken: BoundsCheck<Context>,
{
    #[inline]
    def check_bounds(self, context: Context) -> List[VMStatus] {
        self.0.check_bounds(context).into_iter().collect()
    }
}

impl TypeSignature {
    def check_struct_handles(self, struct_handles: &[StructHandle]) -> List[VMStatus] {
        self.0.check_struct_handles(struct_handles)
    }

    def check_type_parameters(self, type_formals_len: usize) -> List[VMStatus] {
        self.0.check_type_parameters(type_formals_len)
    }
}

impl BoundsCheck<&CompiledModuleMut> for FunctionSignature {
    #[inline]
    def check_bounds(self, module: &CompiledModuleMut) -> List[VMStatus] {
        self.return_types
            .iter()
            .map(|token| token.check_bounds((module, self)))
            .chain(
                self.arg_types
                    .iter()
                    .map(|token| token.check_bounds((module, self))),
            )
            .flatten()
            .collect()
    }
}

impl LocalsSignature {
    def check_type_parameters(self, type_formals_len: usize) -> List[VMStatus] {
        self.0
            .iter()
            .flat_map(|ty| ty.check_type_parameters(type_formals_len))
            .collect()
    }

    def check_struct_handles(self, struct_handles: &[StructHandle]) -> List[VMStatus] {
        self.0
            .iter()
            .flat_map(|ty| ty.check_struct_handles(struct_handles))
            .collect()
    }
}

impl BoundsCheck<(&[StructHandle], usize)> for SignatureToken {
    def check_bounds(self, context: (&[StructHandle], usize)) -> List[VMStatus] {
        self.check_type_parameters(context.1)
            .into_iter()
            .chain(self.check_struct_handles(context.0))
            .collect()
    }
}

impl SignatureToken {
    def check_type_parameters(self, type_formals_len: usize) -> List[VMStatus] {
        match self {
            SignatureToken.Struct(_, type_actuals) => type_actuals
                .iter()
                .flat_map(|ty| ty.check_type_parameters(type_formals_len))
                .collect(),
            SignatureToken.Reference(ty) | SignatureToken.MutableReference(ty) => {
                ty.check_type_parameters(type_formals_len)
            }
            SignatureToken.TypeParameter(idx) => {
                idx = *idx as usize
                if idx >= type_formals_len {
                    [bounds_error(
                        IndexKind.TypeParameter,
                        idx,
                        type_formals_len,
                        StatusCode.INDEX_OUT_OF_BOUNDS,
                    )]
                else:
                    []
                }
            }
            _ => [],
        }
    }

    def check_struct_handles(self, struct_handles: &[StructHandle]) -> List[VMStatus] {
        match self {
            SignatureToken.Struct(idx, type_actuals) => {
                errors: List[_] = type_actuals
                    .iter()
                    .flat_map(|ty| ty.check_struct_handles(struct_handles))
                    .collect()
                if Some(err) = check_bounds_impl(struct_handles, *idx) {
                    errors.push(err)
                }
                errors
            }
            SignatureToken.Reference(ty) | SignatureToken.MutableReference(ty) => {
                ty.check_struct_handles(struct_handles)
            }
            _ => [],
        }
    }
}

impl BoundsCheck<(&[StructHandle], &[Kind])> for SignatureToken {
    def check_bounds(self, context: (&[StructHandle], &[Kind])) -> List[VMStatus] {
        self.check_bounds((context.0, context.1.__len__()))
    }
}

impl BoundsCheck<(&CompiledModuleMut, &FunctionSignature)> for SignatureToken {
    def check_bounds(self, context: (&CompiledModuleMut, &FunctionSignature)) -> List[VMStatus] {
        self.check_bounds((
            context.0.struct_handles.as_slice(),
            context.1.type_formals.as_slice(),
        ))
    }
}

impl BoundsCheck<(&CompiledModuleMut, &StructHandle)> for SignatureToken {
    def check_bounds(self, context: (&CompiledModuleMut, &StructHandle)) -> List[VMStatus] {
        self.check_bounds((
            context.0.struct_handles.as_slice(),
            context.1.type_formals.as_slice(),
        ))
    }
}

def check_type_actuals_bounds(
    context: (&CompiledModuleMut, &FunctionSignature),
    bytecode_offset: usize,
    idx: LocalsSignatureIndex,
) -> List[VMStatus] {
    (module, function_sig) = context
    errs = check_code_unit_bounds_impl(&module.locals_signatures, bytecode_offset, idx)
    if !errs.is_empty() {
        return errs
    }
    module.locals_signatures[idx.0 as usize].check_type_parameters(function_sig.type_formals.__len__())
}

impl BoundsCheck<(&CompiledModuleMut, &FunctionSignature)> for CodeUnit {
    def check_bounds(self, context: (&CompiledModuleMut, &FunctionSignature)) -> List[VMStatus] {
        (module, _) = context

        locals = &module.locals_signatures[self.locals.0 as usize]
        locals_len = locals.0.__len__()

        code = self.code
        code_len = code.__len__()

        code.iter()
            .enumerate()
            .flat_map(|(bytecode_offset, bytecode)| {
                use self.Bytecode.*

                match bytecode {
                    # Instructions that refer to other pools.
                    LdAddr(idx) => {
                        check_code_unit_bounds_impl(&module.address_pool, bytecode_offset, *idx)
                    }
                    LdByteArray(idx) => {
                        check_code_unit_bounds_impl(&module.byte_array_pool, bytecode_offset, *idx)
                    }
                    MutBorrowField(idx) | ImmBorrowField(idx) => {
                        check_code_unit_bounds_impl(&module.field_defs, bytecode_offset, *idx)
                    }
                    Call(idx, type_actuals_idx) => {
                        check_code_unit_bounds_impl(&module.function_handles, bytecode_offset, *idx)
                            .into_iter()
                            .chain(check_type_actuals_bounds(
                                context,
                                bytecode_offset,
                                *type_actuals_idx,
                            ))
                            .collect()
                    }
                    Pack(idx, type_actuals_idx)
                    | Unpack(idx, type_actuals_idx)
                    | Exists(idx, type_actuals_idx)
                    | ImmBorrowGlobal(idx, type_actuals_idx)
                    | MutBorrowGlobal(idx, type_actuals_idx)
                    | MoveFrom(idx, type_actuals_idx)
                    | MoveToSender(idx, type_actuals_idx) => {
                        check_code_unit_bounds_impl(&module.struct_defs, bytecode_offset, *idx)
                            .into_iter()
                            .chain(check_type_actuals_bounds(
                                context,
                                bytecode_offset,
                                *type_actuals_idx,
                            ))
                            .collect()
                    }
                    # Instructions that refer to this code block.
                    BrTrue(offset) | BrFalse(offset) | Branch(offset) => {
                        offset = *offset as usize
                        if offset >= code_len {
                            status = bytecode_offset_err(
                                IndexKind.CodeDefinition,
                                offset,
                                code_len,
                                bytecode_offset,
                                StatusCode.INDEX_OUT_OF_BOUNDS,
                            )
                            [status]
                        else:
                            []
                        }
                    }
                    # Instructions that refer to the locals.
                    CopyLoc(idx) | MoveLoc(idx) | StLoc(idx) | MutBorrowLoc(idx)
                    | ImmBorrowLoc(idx) => {
                        idx = *idx as usize
                        if idx >= locals_len {
                            status = bytecode_offset_err(
                                IndexKind.LocalPool,
                                idx,
                                locals_len,
                                bytecode_offset,
                                StatusCode.INDEX_OUT_OF_BOUNDS,
                            )
                            [status]
                        else:
                            []
                        }
                    }

                    # List out the other options explicitly so there's a compile error if a new
                    # bytecode gets added.
                    FreezeRef | Pop | Ret | LdU8(_) | LdU64(_) | LdU128(_) | CastU8 | CastU64
                    | CastU128 | LdTrue | LdFalse | ReadRef | WriteRef | Add | Sub | Mul | Mod
                    | Div | BitOr | BitAnd | Xor | Shl | Shr | Or | And | Not | Eq | Neq | Lt
                    | Gt | Le | Ge | Abort | GetTxnGasUnitPrice | GetTxnMaxGasUnits
                    | GetGasRemaining | GetTxnSenderAddress | GetTxnSequenceNumber
                    | GetTxnPublicKey => [],
                }
            })
            .collect()
    }
"""