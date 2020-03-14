from .testutils import *
from compiler.ir_to_bytecode.parser import parse_module
from os.path import isfile, join, abspath, dirname
import pytest

def include_str(filename):
    curdir = dirname(__file__)
    path = join(curdir, filename)
    with open(path, 'r') as file:
        return file.read()



def test_compile_native_hash():
    code = include_str("../../compiler/ir_stdlib/modules/hash.mvir")
    _compiled_module = compile_module_string(code)



def test_compile_libra_coin():
    code = include_str("../../compiler/ir_stdlib/modules/libra_coin.mvir")
    _compiled_module = compile_module_string(code)


def test_parse_libra_coin():
    code = include_str("../../compiler/ir_stdlib/modules/libra_account.mvir")
    module = parse_module("libra_account.mvir", code)
    dependency_list = module.get_external_deps()



def test_compile_account_module():
    vector_code = include_str("../../compiler/ir_stdlib/modules/vector.mvir")
    address_util_code = include_str("../../compiler/ir_stdlib/modules/address_util.mvir")
    Uint64_util_code = include_str("../../compiler/ir_stdlib/modules/u64_util.mvir")
    bytearray_util_code = include_str("../../compiler/ir_stdlib/modules/bytearray_util.mvir")

    hash_code = include_str("../../compiler/ir_stdlib/modules/hash.mvir")
    coin_code = include_str("../../compiler/ir_stdlib/modules/libra_coin.mvir")
    time_code = include_str("../../compiler/ir_stdlib/modules/libra_time.mvir")
    ttl_code = include_str("../../compiler/ir_stdlib/modules/libra_transaction_timeout.mvir")
    account_code = include_str("../../compiler/ir_stdlib/modules/libra_account.mvir")

    vector_module = compile_module_string(vector_code)
    address_util_module = compile_module_string(address_util_code)
    Uint64_util_module = compile_module_string(Uint64_util_code)
    bytearray_util_module = compile_module_string(bytearray_util_code)
    hash_module = compile_module_string(hash_code)
    time_module = compile_module_string(time_code)
    ttl_module = compile_module_string_with_deps(ttl_code, [time_module])

    coin_module = compile_module_string(coin_code)

    _compiled_module = compile_module_string_with_deps(
        account_code,
        [
            vector_module,
            hash_module,
            address_util_module,
            Uint64_util_module,
            bytearray_util_module,
            coin_module,
            ttl_module,
        ],
    )




def test_compile_create_account_script():
    code = include_str("../../compiler/ir_stdlib/transaction_scripts/create_account.mvir")
    _compiled_script = compile_script_string_with_stdlib(code)



def test_compile_mint_script():
    code = include_str("../../compiler/ir_stdlib/transaction_scripts/mint.mvir")
    _compiled_script = compile_script_string_with_stdlib(code)



def test_compile_rotate_authentication_key_script():
    code = include_str("../../compiler/ir_stdlib/transaction_scripts/rotate_authentication_key.mvir")
    _compiled_script = compile_script_string_with_stdlib(code)



def test_compile_peer_to_peer_transfer_script():
    code = include_str("../../compiler/ir_stdlib/transaction_scripts/peer_to_peer_transfer.mvir")
    _compiled_script = compile_script_string_with_stdlib(code)

