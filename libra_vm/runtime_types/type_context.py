from __future__ import annotations
from libra_vm.runtime_types.loaded_data import StructDef, Type
from libra_vm.runtime_types.native_structs import NativeStructType
from libra_vm import VMException, format_str
from libra.vm_error import StatusCode, VMStatus
from libra.rustlib import bail
from copy import deepcopy
from typing import List
from canoser import Uint16
from dataclasses import dataclass

@dataclass
class TypeContext:
    v0: List[Type]

    @classmethod
    def identity_mapping(cls, num_type_args: Uint16) -> TypeContext:
        arr = [Type('TypeVariable', i) for i in range(num_type_args)]
        return cls(arr)

    def subst_type(self, ty: Type) -> Type:
        if ty.TypeVariable:
            return self.get_type(ty.value)
        elif ty.Reference:
            return Type('Reference', self.subst_type(ty.value))
        elif ty.MutableReference:
            return Type('MutableReference', self.subst_type(ty.value))
        elif ty.Struct:
            return Type('Struct', self.subst_struct_def(ty.value))
        else:
            return deepcopy(ty)


    def subst_struct_def(self, sdef: StructDef) -> StructDef:
        if sdef.Struct:
            return StructDef.new(
                [self.subst_type(ty) for ty in sdef.value.field_definitions]
            )
        elif sdef.Native:
            return StructDef('Native', NativeStructType(
                sdef.value.tag,
                [self.subst_type(ty) for ty in sdef.value.type_actuals]
            ))
        else:
            bail("unreachable!")


    def get_type(self, idx: Uint16) -> Type:
        try:
            ty = self.v0[idx]
            return deepcopy(ty)
        except Exception:
            msg = f"get type on an invalid type index {idx}"
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(msg))

