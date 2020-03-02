from __future__ import annotations
from libra.vm_error import StatusCode, VMStatus
from libra_vm.errors import verification_error
from libra_vm.file_format import Bytecode, CompiledModule, StructFieldInformation, ModuleAccess
from libra_vm import IndexKind, Opcodes, SerializedNativeStructFlag
from dataclasses import dataclass
from typing import List, Optional, Mapping, Callable, Any, Tuple
from libra.rustlib import flatten

@dataclass
class UnusedEntryChecker:
    module: CompiledModule

    field_defs: List[bool]
    locals_signatures: List[bool]
    type_signatures: List[bool]


    @classmethod
    def new(cls, module: CompiledModule) -> UnusedEntryChecker:
        return cls(
            module,
            field_defs = [False] * module.field_defs().__len__(),
            locals_signatures = [False] * module.locals_signatures().__len__(),
            type_signatures = [False] * module.type_signatures().__len__(),
        )

    def traverse_function_defs(self):
        for func_def in self.module.function_defs():
            if func_def.is_native():
                continue

            self.locals_signatures[func_def.code.locals.v0] = True
            # print(f"{len(self.locals_signatures)} - {func_def.code.locals.v0}")

            for bytecode in func_def.code.code:
                if bytecode.tag in [
                    Opcodes.CALL,
                    Opcodes.PACK,
                    Opcodes.UNPACK,
                    Opcodes.MUT_BORROW_GLOBAL,
                    Opcodes.IMM_BORROW_GLOBAL,
                    Opcodes.EXISTS,
                    Opcodes.MOVE_TO,
                    Opcodes.MOVE_FROM,
                ]:
                    _v, idx = bytecode.value
                    self.locals_signatures[idx.v0] = True



    def traverse_struct_defs(self):
        for struct_def in self.module.struct_defs():
            if struct_def.field_information.tag == SerializedNativeStructFlag.DECLARED:
                field_count = struct_def.field_information.field_count
                fields = struct_def.field_information.fields

                start = fields.v0
                end = start + (field_count)

                for i in range(start, end):
                    self.field_defs[i] = True

                    field_def = self.module.field_defs()[i]
                    self.type_signatures[field_def.signature.v0] = True

    @classmethod
    def collect_errors(cls, pool: List[bool], f: Callable[[usize], VMStatus]) -> List[VMStatus]:
        def lambda0(idx, visited):
            if visited:
                return None
            else:
                return f(idx)
        return [lambda0(idx, visited) for idx, visited in enumerate(pool)]


    def verify(self) -> List[VMStatus]:
        Self = self.__class__
        self.traverse_struct_defs()
        self.traverse_function_defs()

        def lambda0(idx):
            return verification_error(IndexKind.FieldDefinition, idx, StatusCode.UNUSED_FIELD)

        iter_field_defs = Self.collect_errors(self.field_defs, lambda0)

        def lambda1(idx):
            return verification_error(
                IndexKind.LocalsSignature,
                idx,
                StatusCode.UNUSED_LOCALS_SIGNATURE,
            )

        iter_locals_signatures = Self.collect_errors(self.locals_signatures, lambda1)

        def lambda2(idx):
            return verification_error(
                IndexKind.TypeSignature,
                idx,
                StatusCode.UNUSED_TYPE_SIGNATURE,
            )

        iter_type_signatures = Self.collect_errors(self.type_signatures, lambda2)

        return flatten([iter_field_defs, iter_locals_signatures, iter_type_signatures])
