from __future__ import annotations
# use super.{hash, primitive_helpers, signature}
# use crate.{values.{vector, Value},}
from mol.move_vm.types.native_structs import resolve_native_struct
from libra.account_address import Address
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from mol.move_core.types.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, TypeTag
from libra.vm_error import StatusCode, VMStatus
from mol.vm.errors import VMResult
from mol.vm.file_format import FunctionSignature, Kind, SignatureToken, StructHandleIndex
from mol.vm.file_format_common import SerializedType
from mol.vm.gas_schedule import AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, GasUnits, NativeCostIndex
from mol.vm.signature_token_help import *
from mol.vm.vm_exception import VMException
from typing import List, Tuple, Optional, Mapping
from canoser import BoolT, BytesT
from dataclasses import dataclass


# Result of a native function execution that requires charges for execution cost.
#
# An execution that causes an invariant violation would not return a `NativeResult` but
# return a `VMResult` error directly.
# All native functions must return a `VMNativeResult` where an `Err` is returned
# when an error condition is met that should not charge for the execution. A common example
# is a VM invariant violation which should have been forbidden by the verifier.
# Errors (typically user errors and aborts) that are logically part of the function execution
# must be expressed in a `NativeResult` via a cost and a VMStatus.
@dataclass
class NativeResult:
    # The cost for running that function, whether successfully or not.
    cost: GasUnits
    # Result of execution. This is either the return values or the error to report.
    result: List[Value]  # VMResult

    # Return values of a successful execution.
    @classmethod
    def ok(cls, cost: GasUnits, values: List[Value]) -> NativeResult:
        return cls(cost, values)

    # `VMStatus` of a failed execution. The failure is a runtime failure in the function
    # and not an invariant failure of the VM which would raise a `VMResult` error directly.
    @classmethod
    def err(cls, cost: GasUnits, err: VMStatus) -> NativeResult:
        return cls(cost, err)


# Struct representing the expected definition for a native function.
@dataclass
class NativeFunction:
    # Given the vector of aguments, it executes the native function.
    dispatch: Callable[[List[TypeTag], List[Value], CostTable], NativeResult]
    # The signature as defined in it's declaring module.
    # It should NOT be generally inspected outside of it's declaring module as the various
    # class handle indexes are not remapped into the local context.
    expected_signature: FunctionSignature

    # Returns the number of arguments to the native function, derived from the expected signature.

    def num_args(self) -> usize:
        return self.expected_signature.arg_types.__len__()

    def signature(self) -> FunctionSignature:
        return self.expected_signature



def native_gas(table: CostTable, key: NativeCostIndex, size: usize) -> GasUnits:
    gas_amt = table.native_cost(key)
    memory_size = AbstractMemorySize.new(size)
    return gas_amt.total().mul(memory_size)


def pop_arg(arguments, ty):
    if ty == bool:
        ty = BoolT
    elif ty == bytes:
        ty = BytesT()
    return arguments.pop().value_as(ty)
