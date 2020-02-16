from __future__ import annotations
from libra_vm.runtime_types.native_functions import hashf, primitive_helpers, signature
from libra_vm.runtime_types.native_functions import pop_arg, native_gas, NativeResult, NativeFunction
from libra_vm.runtime_types.values import vector, Value
from libra_vm.runtime_types.native_structs import resolve_native_struct
from libra.account_address import Address
from libra.account_config import AccountConfig
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, TypeTag
from libra.vm_error import StatusCode, VMStatus
from libra_vm.errors import VMResult
from libra_vm.file_format import FunctionSignature, Kind, SignatureToken, StructHandleIndex
from libra_vm.file_format_common import SerializedType
from libra_vm.gas_schedule import AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, GasUnits, NativeCostIndex
from libra_vm.signature_token_help import *
from libra_vm.vm_exception import VMException
from typing import List, Tuple, Optional, Mapping
from dataclasses import dataclass
from libra.rustlib import assert_equal


# Looks up the expected native function definition from the module id (address and module) and
# function name where it was expected to be declared.
def resolve_native_function(
    module: ModuleId,
    function_name: IdentStr,
) -> Optional[NativeFunction]:
    return NATIVE_FUNCTION_MAP[module][function_name]



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


# Helper for finding expected class handle index.
def tstruct(
    addr: Address,
    module_name: str,
    function_name: str,
    args: List[SignatureToken],
) -> SignatureToken:
    mid = ModuleId(addr, module_name)
    native_struct = resolve_native_struct(mid, function_name)
    idx = native_struct.expected_index
    # TODO assert kinds match
    assert_equal(args.__len__(), native_struct.expected_type_formals.__len__())
    return SignatureToken(SerializedType.STRUCT, struct=(idx, args))


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
    [BYTEARRAY],
    [BYTEARRAY]
)

add_native_function_to_map(
    "Hash",
    "sha3_256",
    hashf.native_sha3_256,
    [BYTEARRAY],
    [BYTEARRAY]
)

add_native_function_to_map(
    "Signature",
    "ed25519_verify",
    signature.native_ed25519_signature_verification,
    [BYTEARRAY, BYTEARRAY, BYTEARRAY],
    [BOOL]
)

add_native_function_to_map(
    "Signature",
    "ed25519_threshold_verify",
    signature.native_ed25519_threshold_signature_verification,
    [BYTEARRAY, BYTEARRAY, BYTEARRAY, BYTEARRAY],
    [U64]
)

add_native_function_to_map(
    "AddressUtil",
    "address_to_bytes",
    primitive_helpers.native_address_to_bytes,
    [ADDRESS],
    [BYTEARRAY]
)

add_native_function_to_map(
    "U64Util",
    "Uint64_to_bytes",
    primitive_helpers.native_Uint64_to_bytes,
    [U64],
    [BYTEARRAY]
)

add_native_function_to_map(
    "BytearrayUtil",
    "bytearray_concat",
    primitive_helpers.native_bytearray_concat,
    [BYTEARRAY, BYTEARRAY],
    [BYTEARRAY]
)

add_native_function_to_map2(
    "Vector",
    "length",
    vector.native_length,
    [Kind.All],
    [Reference(tstruct(
        AccountConfig.core_code_address_bytes(),
        "Vector",
        "T",
        [TypeParameter(0)]
    ))],
    [U64]
)

add_native_function_to_map2(
    "Vector",
    "empty",
    vector.native_empty,
    [Kind.All],
    [],
    [tstruct(AccountConfig.core_code_address_bytes(), "Vector", "T", [TypeParameter(0)]), ]
)

add_native_function_to_map2(
    "Vector",
    "borrow",
    vector.native_borrow,
    [Kind.All],
    [
        Reference(tstruct(
            AccountConfig.core_code_address_bytes(),
            "Vector",
            "T",
            [TypeParameter(0)]
        )),
        U64
    ],
    [Reference(TypeParameter(0))]
)

add_native_function_to_map2(
    "Vector",
    "borrow_mut",
    vector.native_borrow,
    [Kind.All],
    [
        MutableReference(tstruct(
            AccountConfig.core_code_address_bytes(),
            "Vector",
            "T",
            [TypeParameter(0)]
        )),
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
        MutableReference(tstruct(
            AccountConfig.core_code_address_bytes(),
            "Vector",
            "T",
            [TypeParameter(0)]
        )),
        TypeParameter(0),
    ],
    []
)

add_native_function_to_map2(
    "Vector",
    "pop_back",
    vector.native_pop,
    [Kind.All],
    [MutableReference(tstruct(
        AccountConfig.core_code_address_bytes(),
        "Vector",
        "T",
        [TypeParameter(0)]
    ))],
    [TypeParameter(0)]
)

add_native_function_to_map2(
    "Vector",
    "destroy_empty",
    vector.native_destroy_empty,
    [Kind.All],
    [tstruct(AccountConfig.core_code_address_bytes(), "Vector", "T", [TypeParameter(0)])],
    []
)


add_native_function_to_map2(
    "Vector",
    "swap",
    vector.native_swap,
    [Kind.All],
    [
        MutableReference(tstruct(
            AccountConfig.core_code_address_bytes(),
            "Vector",
            "T",
            [TypeParameter(0)]
        )),
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
    [BYTEARRAY, U64, TypeParameter(0)],
    []
)

# LibraAccount
add_native_function_to_map(
    "LibraAccount",
    "save_account",
    gen_lambda("save_account does not have a native implementation"),
    [
        ADDRESS,
        # this is LibraAccount.T which happens to be the first class handle in the
        # binary.
        # TODO: current plan is to rework the description of the native function
        # by using the binary directly and have functions that fetch the arguments
        # go through the signature for extra verification. That is the plan if perf
        # and the model look good.
        Struct((StructHandleIndex(0), [])),
    ],
    []
)

