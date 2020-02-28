from __future__ import annotations
from libra_vm.runtime_types.native_functions import pop_arg, native_gas, NativeResult
from libra_vm.runtime_types.values import Value
from libra_vm.vm_exception import VMException
from libra_vm.gas_schedule import CostTable, NativeCostIndex
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
    arg2 = pop_arg(arguments, ByteArray)
    arg1 = pop_arg(arguments, ByteArray)
    return_val = arg1.extend(arg2)

    cost = native_gas(
        cost_table,
        NativeCostIndex.BYTEARRAY_CONCAT,
        return_val.__len__(),
    )
    return_values = [Value.byte_array(return_val)]
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
    return_values = [Value.byte_array(return_val)]
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
    return_values = [Value.byte_array(bytearray(return_val))]
    return NativeResult.ok(cost, return_values)

