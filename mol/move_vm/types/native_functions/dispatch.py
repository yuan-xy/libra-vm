from __future__ import annotations
from mol.move_vm.types.native_functions import hashf, primitive_helpers, signature
from mol.move_vm.types.native_functions import pop_arg, native_gas, NativeResult, NativeFunction
from mol.move_vm.types.values import Value
import mol.move_vm.types.vector as vector
from mol.move_vm.types.native_structs import resolve_native_struct
from libra.account_address import Address
from libra.account_config import AccountConfig
from mol.move_core.types.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, TypeTag
from libra.vm_error import StatusCode, VMStatus
from mol.vm.errors import VMResult
from mol.vm.file_format import ModuleAccess, FunctionSignature, Kind, SignatureToken, StructHandleIndex
from mol.vm.file_format_common import SerializedType
from mol.vm.gas_schedule import AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, GasUnits, NativeCostIndex
from mol.vm.signature_token_help import *
from mol.vm.vm_exception import VMException
from mol.vm.views import ModuleView
from typing import List, Tuple, Optional, Mapping
from dataclasses import dataclass
from libra.rustlib import assert_equal

#TTODO: Refactor Native Functions, This allows for a generic singature function. commit 18a1734e

# Looks up the expected native function definition from the module id (address and module) and
# function name where it was expected to be declared.
def resolve_native_function(
    module: ModuleId,
    function_name: IdentStr,
) -> Optional[NativeFunction]:
    try:
        return NATIVE_FUNCTION_MAP[module][function_name]
    except KeyError:
        return None


def add_native_function(m, addr, module, name, dis, args, ret, kinds=[]):
    expected_signature = FunctionSignature(
        return_types=ret,
        arg_types=args,
        type_formals=kinds,
    )
    f = NativeFunction(
        dispatch=dis,
        expected_signature=expected_signature,
    )
    mid = ModuleId(addr, module)
    if mid not in m:
        m[mid] = {}
    assert name not in m[mid]
    m[mid][name] = f


NativeFunctionMap = Mapping[ModuleId, Mapping[Identifier, NativeFunction]]

NATIVE_FUNCTION_MAP: NativeFunctionMap = {}


def add_native_function_to_map(module, name, dis, args, ret):
    addr = AccountConfig.core_code_address_bytes()
    add_native_function(NATIVE_FUNCTION_MAP, addr, module, name, dis, args, ret)

def add_native_function_to_map2(module, name, dis, kind, args, ret):
    addr = AccountConfig.core_code_address_bytes()
    add_native_function(NATIVE_FUNCTION_MAP, addr, module, name, dis, args, ret, kind)




add_native_function_to_map(
    "Hash",
    "sha2_256",
    hashf.native_sha2_256,
    [VectorU8],
    [VectorU8]
)

add_native_function_to_map(
    "Hash",
    "sha3_256",
    hashf.native_sha3_256,
    [VectorU8],
    [VectorU8]
)

add_native_function_to_map(
    "Signature",
    "ed25519_verify",
    signature.native_ed25519_signature_verification,
    [VectorU8, VectorU8, VectorU8],
    [BOOL]
)

add_native_function_to_map(
    "Signature",
    "ed25519_threshold_verify",
    signature.native_ed25519_threshold_signature_verification,
    [VectorU8, VectorU8, VectorU8, VectorU8],
    [U64]
)

add_native_function_to_map(
    "AddressUtil",
    "address_to_bytes",
    primitive_helpers.native_address_to_bytes,
    [ADDRESS],
    [VectorU8]
)

add_native_function_to_map(
    "U64Util",
    "u64_to_bytes",
    primitive_helpers.native_Uint64_to_bytes,
    [U64],
    [VectorU8]
)

add_native_function_to_map2(
    "Vector",
    "length",
    vector.native_length,
    [Kind.All],
    [Reference(Vector(TypeParameter(0)))],
    [U64]
)

add_native_function_to_map2(
    "Vector",
    "empty",
    vector.native_empty,
    [Kind.All],
    [],
    [Vector(TypeParameter(0))]
)

add_native_function_to_map2(
    "Vector",
    "borrow",
    vector.native_borrow,
    [Kind.All],
    [Reference(Vector(TypeParameter(0))), U64],
    [Reference(TypeParameter(0))]
)

add_native_function_to_map2(
    "Vector",
    "borrow_mut",
    vector.native_borrow,
    [Kind.All],
    [
        MutableReference(Vector(TypeParameter(0))),
        U64
    ],
    [MutableReference(TypeParameter(0))]
)

add_native_function_to_map2(
    "Vector",
    "push_back",
    vector.native_push_back,
    [Kind.All],
    [
        MutableReference(Vector(TypeParameter(0))),
        TypeParameter(0),
    ],
    []
)

add_native_function_to_map2(
    "Vector",
    "pop_back",
    vector.native_pop,
    [Kind.All],
    [MutableReference(Vector(TypeParameter(
        0
    )))],
    [TypeParameter(0)]
)

add_native_function_to_map2(
    "Vector",
    "destroy_empty",
    vector.native_destroy_empty,
    [Kind.All],
    [Vector(TypeParameter(0))],
    []
)


add_native_function_to_map2(
    "Vector",
    "swap",
    vector.native_swap,
    [Kind.All],
    [
        MutableReference(Vector(TypeParameter(0))),
        U64,
        U64,
    ],
    []
)

# TODO: both API bolow are directly implemented in the interepreter as we lack a
# good mechanism to expose certain API to native functions.
# Specifically we need access to some frame information (e.g. type instantiations) and
# access to the data store.
# Maybe marking native functions in a certain way (e.g `system` or similar) may
# be a way for the VM to force a given argument to the native implementation.
# Alternative models are fine too...

def raise_(ex):
    raise ex

def gen_lambda(msg):
    return lambda _x, _y, _z : raise_(VMException(VMStatus(StatusCode.UNREACHABLE).with_message(msg)))


# Event
add_native_function_to_map2(
    "LibraAccount",
    "write_to_event_store",
    gen_lambda("write_to_event_store does not have a native implementation"),
    [Kind.Unrestricted],
    [VectorU8, U64, TypeParameter(0)],
    []
)

def save_account_arg_types(m):
    #TTODO:
    breakpoint()
    self_t_idx = struct_handle_idx(
        m,
        AccountConfig.core_code_address_bytes(),
        AccountConfig.ACCOUNT_MODULE_NAME,
        AccountConfig.ACCOUNT_STRUCT_NAME,
    )
    balance_t_idx = struct_handle_idx(
        m,
        AccountConfig.core_code_address_bytes(),
        AccountConfig.ACCOUNT_MODULE_NAME,
        AccountConfig.ACCOUNT_BALANCE_STRUCT_NAME,
    )
    arg_types = [
        Struct((balance_t_idx, [TypeParameter(0)])),
        Struct((self_t_idx, [])),
        Address,
    ]
    return arg_types

# Helper for finding non-native struct handle index
def struct_handle_idx(
    m: ModuleView,
    module_address: Address,
    module_name: str,
    name: str,
) -> Optional[StructHandleIndex]:
    for (idx, handle) in enumerate(m.struct_handles()):
        if handle.name() == name \
            and handle.module_id().name() == module_name \
            and handle.module_id().address() == module_address:
            return StructHandleIndex.new(idx)
        
    return None

# LibraAccount
add_native_function_to_map2(
    "LibraAccount",
    "save_account",
    gen_lambda("save_account does not have a native implementation"),
    [Kind.All],
    save_account_arg_types,
    []
)
