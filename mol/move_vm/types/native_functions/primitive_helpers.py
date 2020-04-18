from __future__ import annotations
from mol.move_vm.types.native_functions import pop_arg, native_gas, NativeResult
from mol.move_vm.types.values import Value
from mol.vm.vm_exception import VMException
from mol.vm.gas_schedule import CostTable, NativeCostIndex
from libra.account_address import Address
from libra.language_storage import TypeTag
from libra.vm_error import StatusCode, VMStatus
from canoser import Uint64, Uint32
from libra.rustlib import usize
from typing import List, Tuple, Optional, Mapping

def check_arg_number(arguments: List[Value], num: int, name: str):
    length = arguments.__len__()
    if length != num:
        msg = f"wrong number of arguments for {name} expected {num} found {length}"
        raise VMException(VMStatus(StatusCode.UNREACHABLE).with_message(msg))


def native_bytearray_concat(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    check_arg_number(arguments, 2, 'bytearray_concat')
    arg2 = pop_arg(arguments, bytes)
    arg1 = pop_arg(arguments, bytes)
    return_val = arg1+arg2

    cost = native_gas(
        cost_table,
        NativeCostIndex.BYTEARRAY_CONCAT,
        return_val.__len__(),
    )
    return_values = [Value.vector_u8(return_val)]
    return NativeResult.ok(cost, return_values)


def native_address_to_bytes(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    check_arg_number(arguments, 1, 'address_to_bytes')
    arg = pop_arg(arguments, Address)
    return_val = arg

    cost = native_gas(
        cost_table,
        NativeCostIndex.ADDRESS_TO_BYTES,
        return_val.__len__(),
    )
    return_values = [Value.vector_u8(return_val)]
    return NativeResult.ok(cost, return_values)


def native_Uint64_to_bytes(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    check_arg_number(arguments, 1, 'u64_to_bytes')
    arg = pop_arg(arguments, Uint64)
    return_val = arg.to_bytes(8, byteorder="little", signed=False)

    cost = native_gas(cost_table, NativeCostIndex.U64_TO_BYTES, return_val.__len__())
    return_values = [Value.vector_u8(return_val)]
    return NativeResult.ok(cost, return_values)

