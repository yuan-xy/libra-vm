from libra_vm.runtime.identifier import resource_storage_key
from libra_vm.file_format import ModuleAccess
from libra_vm.file_format import CompiledModule, StructDefinitionIndex, TableIndex
from libra.language_storage import ModuleId, StructTag
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
    curdir = dirname(__file__)
    sdir = join(curdir, "../vm/stdlib_modules")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        do_test_module(filename)

def do_test_module(filename):
    print(filename)
    with open(filename, 'r') as file:
        amap = json.load(file)
        code = bytes(amap['code'])
        obj = CompiledModule.deserialize(code)
        identifier_serializer_roundtrip(obj)


