from move_vm.types.identifier import resource_storage_key
from vm.file_format import ModuleAccess
from vm.file_format import CompiledModule, StructDefinitionIndex, TableIndex
from libra.language_storage import ModuleId, StructTag
from stdlib import build_stdlib_map
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname



def identifier_serializer_roundtrip(module):
    module_id = module.self_id()
    serialized_key = module_id.serialize()
    deserialized_module_id = ModuleId.deserialize(serialized_key)
    assert (module_id == deserialized_module_id)

    for i in range(module.struct_defs().__len__()):
        struct_key = resource_storage_key(module, StructDefinitionIndex(i), [])
        serialized_key = struct_key.serialize()
        deserialized_struct_key = StructTag.deserialize(serialized_key)
        assert (struct_key == deserialized_struct_key)
        print(struct_key)


def test_std_module():
    for file, module in build_stdlib_map().items():
        print(file)
        identifier_serializer_roundtrip(module)

