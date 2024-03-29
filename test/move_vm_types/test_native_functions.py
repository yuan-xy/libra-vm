from mol.move_vm.types.native_functions.dispatch import *
from mol.move_vm.types.native_functions import NativeFunction

from libra.language_storage import ModuleId, TypeTag
from libra import AccountConfig, Address

def test_native_function():
    assert len(NATIVE_FUNCTION_MAP) == 6
    hashm = ModuleId(AccountConfig.core_code_address_bytes(), "Hash")
    func_map = NATIVE_FUNCTION_MAP[hashm]
    assert len(func_map) == 2
    assert isinstance(func_map['sha2_256'], NativeFunction)
