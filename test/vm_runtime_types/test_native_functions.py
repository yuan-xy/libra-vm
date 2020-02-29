from libra_vm.runtime_types.native_functions.dispatch import *
from libra_vm.runtime_types.native_functions import NativeFunction

from libra.language_storage import ModuleId, TypeTag
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS

def test_native_function():
    assert len(NATIVE_FUNCTION_MAP) == 7
    hashm = ModuleId(CORE_CODE_ADDRESS, "Hash")
    func_map = NATIVE_FUNCTION_MAP[hashm]
    assert len(func_map) == 2
    assert isinstance(func_map['sha2_256'], NativeFunction)
