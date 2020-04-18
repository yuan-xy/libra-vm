from __future__ import annotations
from mol.move_vm.types.loaded_data import Type
from mol.vm.file_format import Kind, StructHandleIndex
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from mol.move_core.types.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId
from canoser import RustEnum, Struct
from typing import List, Mapping, Optional
from dataclasses import dataclass


class NativeStructTag(RustEnum):
    _enums = []


# TODO: Clean this up when we promote Vector to a primitive type.
#[derive(Debug, Eq, PartialEq, Clone, Serialize, Deserialize)]
class NativeStructType(Struct):
    _fields = [
        ('tag', NativeStructTag),
        ('type_actuals', [Type])
    ]



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
# TODO: native structs are now deprecated. Remove them.
def resolve_native_struct(
    module: ModuleId,
    struct_name: IdentStr,
) -> Optional[NativeStruct]:
    return None

