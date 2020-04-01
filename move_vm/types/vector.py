from __future__ import annotations
from move_vm.types.native_functions import native_gas, NativeResult, NativeFunction
from move_vm.types.loaded_data import StructDef, Type
from move_vm.types.values import *

from move_vm.types.native_structs import NativeStructTag, NativeStructType
from libra.account_address import Address, ADDRESS_LENGTH
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.language_storage import ModuleId, TypeTag, StructTag
from libra.vm_error import StatusCode, VMStatus, SubStatus
from libra_vm.errors import *
from libra_vm.file_format import SignatureToken
from libra_vm.file_format_common import SerializedType
from libra_vm.gas_schedule import (
    words_in, AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, NativeCostIndex,
    CONST_SIZE, REFERENCE_SIZE, STRUCT_SIZE
    )
#from libra_vm.signature_token_help import *
from libra_vm.vm_exception import VMException
from typing import List, Tuple, Optional, Mapping
from dataclasses import dataclass
from copy import deepcopy
from libra.rustlib import assert_equal
from canoser import Uint8, Uint64, Uint128, BoolT

"""
/***************************************************************************************
*
* Vector
*
*   Native function imeplementations of the Vector module.
*
*   TODO: split the code into two parts:
*         1) Internal vector APIs that define & implements the core operations
             (and operations only).
*         2) Native function adapters that the dispatcher can call into. These will
*            check if arguments are valid and deal with gas metering.
*
**************************************************************************************/
"""

INDEX_OUT_OF_BOUNDS: Uint64 = SubStatus.NFE_VECTOR_ERROR_BASE + 1
POP_EMPTY_VEC: Uint64 = SubStatus.NFE_VECTOR_ERROR_BASE + 2
DESTROY_NON_EMPTY_VEC: Uint64 = SubStatus.NFE_VECTOR_ERROR_BASE + 3

def ensure_len(v, expected_len, atype, fn):
    actual_len = v.__len__()
    if actual_len != expected_len:
        msg = format_str(
            "wrong number of {} for {} expected {} found {}",
            (atype),
            (fn),
            expected_len,
            actual_len,
        )
        raise VMException(VMStatus(StatusCode.UNREACHABLE).with_message(msg))

def pop_arg_front(arguments, t):
    return arguments.pop(0).value_as(t)

def err_vector_elem_ty_mismatch(tag, val):
    raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
            .with_message("vector elem type mismatch -- expected {}, got {}".format(
                tag, val
            )))


def native_empty(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "empty")
    ensure_len(args, 0, "arguments", "empty")

    cost = native_gas(cost_table, NativeCostIndex.EMPTY, 1)
    if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool'):
        container = Container(ty_args[0].enum_name, [])
    else:
        container = Container('General', [])

    return NativeResult.ok(
        cost,
        [ValueImpl.new_container(container)],
    )


def native_length(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "length")
    ensure_len(args, 1, "arguments", "length")

    cost = native_gas(cost_table, NativeCostIndex.LENGTH, 1)
    r = pop_arg_front(args, ContainerRef)
    v = r.borrow().v0
    if type(ty_args[0]) == TypeTag and type(v) == Container:
        if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool')\
            and v.enum_name == ty_args[0].enum_name:
            length = v.value.__len__()
        elif ty_args[0].enum_name in ('Struct', 'ByteArray', 'Address')\
            and v.enum_name == 'General':
            length = v.value.__len__()
        else:
            err_vector_elem_ty_mismatch(ty_args[0], v)
    else:
        err_vector_elem_ty_mismatch(ty_args[0], v)

    return NativeResult.ok(cost, [Value.Uint64(length)])


def native_push_back(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "push back")
    ensure_len(args, 2, "arguments", "push back")

    r = pop_arg_front(args, ContainerRef)
    v = r.borrow_mut().v0
    e = args.pop(0)

    cost = cost_table.native_cost(NativeCostIndex.PUSH_BACK).total().mul(e.size())

    if type(ty_args[0]) == TypeTag and type(v) == Container:
        if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool')\
            and v.enum_name == ty_args[0].enum_name:
            v.value.append(e.value)
        elif ty_args[0].enum_name in ('Struct', 'ByteArray', 'Address')\
            and v.enum_name == 'General':
            v.value.append(e)
        else:
            breakpoint()
            err_vector_elem_ty_mismatch(ty_args[0], v)
    else:
        err_vector_elem_ty_mismatch(ty_args[0], v)

    return NativeResult.ok(cost, [])


def native_borrow(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "borrow")
    ensure_len(args, 2, "arguments", "borrow")

    cost = native_gas(cost_table, NativeCostIndex.BORROW, 1)
    r = pop_arg_front(args, ContainerRef)
    v = r.borrow().v0
    idx = pop_arg_front(args, Uint64)

    # TODO: check if the type tag matches the real type
    if idx >= v.__len__():
        return NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(INDEX_OUT_OF_BOUNDS),
        )

    v = r.borrow_elem(idx)
    return NativeResult.ok(cost, [v])


def native_pop(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "pop")
    ensure_len(args, 1, "arguments", "pop")

    cost = native_gas(cost_table, NativeCostIndex.POP_BACK, 1)
    r = pop_arg_front(args, ContainerRef)
    v = r.borrow_mut().v0

    def err_pop_empty_vec():
        return NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(POP_EMPTY_VEC),
        )

    if type(ty_args[0]) == TypeTag and type(v) == Container:
        if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool')\
            and v.enum_name == ty_args[0].enum_name:
            if v:
                res = ValueImpl(v.enum_name, v.value.pop())
            else:
                return err_pop_empty_vec()
        elif ty_args[0].enum_name in ('Struct', 'ByteArray', 'Address')\
            and v.enum_name == 'General':
            if v:
                res = v.value.pop()
            else:
                return err_pop_empty_vec()
        else:
            err_vector_elem_ty_mismatch(ty_args[0], v)
    else:
        err_vector_elem_ty_mismatch(ty_args[0], v)

    return NativeResult.ok(cost, [res])


def native_destroy_empty(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "destroy empty")
    ensure_len(args, 1, "arguments", "destroy empty")

    cost = native_gas(cost_table, NativeCostIndex.DESTROY_EMPTY, 1)
    v = args.pop(0).value_as(Container)

    if type(ty_args[0]) == TypeTag and type(v) == Container:
        if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool')\
            and v.enum_name == ty_args[0].enum_name:
            length = v.value.__len__()
        elif ty_args[0].enum_name in ('Struct', 'ByteArray', 'Address')\
            and v.enum_name == 'General':
            length = v.value.__len__()
        else:
            err_vector_elem_ty_mismatch(ty_args[0], v)
    else:
        err_vector_elem_ty_mismatch(ty_args[0], v)

    if length < 1:
        return NativeResult.ok(cost, [])
    else:
        return NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(DESTROY_NON_EMPTY_VEC),
        )


def native_swap(
    ty_args: List[TypeTag],
    args: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    ensure_len(ty_args, 1, "type arguments", "swap")
    ensure_len(args, 3, "arguments", "swap")

    cost = native_gas(cost_table, NativeCostIndex.SWAP, 1)
    r = pop_arg_front(args, ContainerRef)
    v = r.borrow_mut().v0
    idx1 = pop_arg_front(args, Uint64)
    idx2 = pop_arg_front(args, Uint64)

    if type(ty_args[0]) == TypeTag and type(v) == Container:
        if idx1 >= v.__len__() or idx2 >= v.__len__():
            return NativeResult.err(
                cost,
                VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(INDEX_OUT_OF_BOUNDS),
            )
        if ty_args[0].enum_name in ('U8', 'U64', 'U128', 'Bool')\
            and v.enum_name == ty_args[0].enum_name:
            tmp = v.value[idx1]
            v.value[idx1] = v.value[idx2]
            v.value[idx2] = tmp
        elif ty_args[0].enum_name in ('Struct', 'ByteArray', 'Address')\
            and v.enum_name == 'General':
            tmp = v.value[idx1]
            v.value[idx1] = v.value[idx2]
            v.value[idx2] = tmp
        else:
            err_vector_elem_ty_mismatch(ty_args[0], v)
    else:
        err_vector_elem_ty_mismatch(ty_args[0], v)

    return NativeResult.ok(cost, [])

