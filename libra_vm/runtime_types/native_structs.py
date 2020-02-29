from __future__ import annotations
from libra_vm.runtime_types.loaded_data import Type
from libra_vm.file_format import Kind, StructHandleIndex
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId
from canoser import RustEnum, Struct
from typing import List, Mapping, Optional
from dataclasses import dataclass


class NativeStructTag(RustEnum):
    _enums = [
        ('Vector', None)
    ]


# TODO: Clean this up when we promote Vector to a primitive type.
#[derive(Debug, Eq, PartialEq, Clone, Serialize, Deserialize)]
class NativeStructType(Struct):
    _fields = [
        ('tag', NativeStructTag),
        ('type_actuals', [Type])
    ]

    @classmethod
    def new_vec(cls, ty: Type) -> NativeStructType:
        return NativeStructType(NativeStructTag('Vector'), [ty])



#-----dispatch.rs-----
# Struct representing the expected definition for a native struct
@dataclass
class NativeStruct:
    # The expected boolean indicating if it is a nominal resource or not
    expected_nominal_resource: bool
    # The expected kind constraints of the type parameters.
    expected_type_formals: List[Kind]
    # The expected index for the struct
    # Helpful for ensuring proper typing of native functions
    expected_index: StructHandleIndex
    # Kind of the NativeStruct,
    struct_type: NativeStructType


# Looks up the expected native struct definition from the module id (address and module) and
# function name where it was expected to be declared
def resolve_native_struct(
    module: ModuleId,
    struct_name: IdentStr,
) -> Optional[NativeStruct]:
    return NATIVE_STRUCT_MAP[module][struct_name]


NativeStructMap = Mapping[ModuleId, Mapping[Identifier, NativeStruct]]


def add_native_map(m, addr, module, name, resource, ty_kinds, tag):
    ty_args = [Type('TypeVariable', id) for (id, _) in enumerate(ty_kinds)]
    mid = ModuleId(addr, module)
    if mid in m:
        struct_table = m[mid]
    else:
        struct_table = {}
        m[mid] = struct_table
    expected_index = StructHandleIndex(struct_table.__len__())

    s = NativeStruct(
        expected_nominal_resource = resource,
        expected_type_formals = ty_kinds,
        expected_index = expected_index,
        struct_type = NativeStructType(tag, ty_args),
    )
    assert name not in struct_table
    struct_table[name] = s
    return m

NATIVE_STRUCT_MAP = add_native_map(
    {},
    CORE_CODE_ADDRESS,
    "Vector",
    "T",
    False,
    [Kind.All],
    NativeStructTag('Vector'),
)
