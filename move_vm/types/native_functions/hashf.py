from __future__ import annotations
from move_vm.types.native_functions import pop_arg, native_gas, NativeResult
from move_vm.types.values import Value
from libra_vm.vm_exception import VMException
from libra_vm.gas_schedule import CostTable, NativeCostIndex
from libra.hasher import HashValue, new_sha3_256
from libra.language_storage import TypeTag
from libra.vm_error import StatusCode, VMStatus
from libra_vm import signature_token_help
import hashlib
from typing import List, Tuple, Optional, Mapping
from dataclasses import dataclass


def native_sha2_256(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    if arguments.__len__() != 1:
        msg = f"wrong number of arguments for sha2_256 expected 1 found {len(arguments)}"
        raise VMException(VMStatus(StatusCode.UNREACHABLE).with_message(msg))

    hash_arg = pop_arg(arguments, bytes)
    cost = native_gas(cost_table, NativeCostIndex.SHA2_256, hash_arg.__len__())
    sha2 = hashlib.sha256()
    sha2.update(bytes(hash_arg))
    hash_vec = sha2.digest()
    return_values = [Value.vector_u8(hash_vec)]
    return NativeResult.ok(cost, return_values)



def native_sha3_256(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> VMNativeResult:
    if arguments.__len__() != 1:
        msg = f"wrong number of arguments for sha3_256 expected 1 found {len(arguments)}"
        raise VMException(VMStatus(StatusCode.UNREACHABLE).with_message(msg))

    hash_arg = pop_arg(arguments, bytes)
    cost = native_gas(cost_table, NativeCostIndex.SHA3_256, hash_arg.__len__())
    sha3 = new_sha3_256()
    sha3.update(bytes(hash_arg))
    hash_vec = sha3.digest()
    return_values = [Value.vector_u8(hash_vec)]
    return NativeResult.ok(cost, return_values)

