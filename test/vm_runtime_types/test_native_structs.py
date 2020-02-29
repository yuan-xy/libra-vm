from libra_vm.runtime_types.native_structs import *
from libra.language_storage import ModuleId

def test_native():
    assert len(NATIVE_STRUCT_MAP) == 1
    module = ModuleId(CORE_CODE_ADDRESS, "Vector")
    amap = NATIVE_STRUCT_MAP[module]
    assert "T" in amap
