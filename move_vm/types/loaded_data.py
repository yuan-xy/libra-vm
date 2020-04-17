from __future__ import annotations
from canoser import Struct, RustEnum, Uint16
from typing import List

# Loaded representation for runtime types.


# Resolved form of runtime types.
class Type(RustEnum):  # order not same with SerializedType
    _enums = [
        ('Bool', None),
        ('U8', None),
        ('U64', None),
        ('U128', None),
        ('Address', None),
        ('Vector', 'move_vm.types.loaded_data.Type'),
        ('Struct', 'move_vm.types.loaded_data.StructDef'),
        ('Reference', 'move_vm.types.loaded_data.Type'),
        ('MutableReference', 'move_vm.types.loaded_data.Type'),
        ('TypeVariable', Uint16)
    ]




# Loaded representation for Move struct definition.

# Do not implement Clone for this -- the outer StructDef should be Arc'd.
class StructDefInner(Struct):
    _fields = [('field_definitions', [Type])]


# Note that this data structure can represent recursive types but will end up creating reference
# cycles, which is bad. Other parts of the system disallow recursive types for now, but this may
# need to be handled more explicitly in the future.
#  Resolved form of struct definition.

class StructDef(RustEnum):
    _enums = [
        ('Struct', StructDefInner),
        ('Native', 'move_vm.types.native_structs.NativeStructType')
    ]

    @classmethod
    def new(cls, field_definitions: List[Type]) -> StructDef:
        return StructDef(
            'Struct',
            StructDefInner(field_definitions)
        )



