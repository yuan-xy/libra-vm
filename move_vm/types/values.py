from __future__ import annotations
from move_vm.types.ref_cell import RefCell, Ref, RefMut, RefCellCanoser
from move_vm.types.native_functions import native_gas, NativeResult, NativeFunction
from move_vm.types.loaded_data import StructDef, Type

from libra.account_address import Address, ADDRESS_LENGTH
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.language_storage import ModuleId, TypeTag
from libra.vm_error import StatusCode, VMStatus, SubStatus
from vm.errors import *
from vm.file_format import SignatureToken
from vm.file_format_common import SerializedType
from vm.gas_schedule import (
    words_in, AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, NativeCostIndex,
    CONST_SIZE, REFERENCE_SIZE, STRUCT_SIZE, add_lambda
    )
from vm.signature_token_help import VectorU8
from vm.vm_exception import VMException
from typing import List, Tuple, Optional, Mapping
from dataclasses import dataclass
from copy import deepcopy
from libra.rustlib import assert_equal, bail, ensure
from canoser import Uint8, Uint64, Uint128, RustEnum, Cursor, BoolT, BytesT
from canoser import Struct as CanoserStruct
import traceback
import gc
import logging

logger = logging.getLogger(__name__)

"""
/***************************************************************************************
 *
 * Internal Types
 *
 *   Internal representation of the Move value calculus. These types are abstractions
 *   over the concrete Move concepts and may carry additonal information that is not
 *   defined by the language, but required by the implementation.
 *
 **************************************************************************************/
"""

class ContainerRefCell(RefCellCanoser):
    delegate_type = 'move_vm.types.values.Container'


# Runtime representation of a Move value.

class ValueImpl(RustEnum):
    _enums = [
        ('Invalid', None),
        ('Bool', bool),
        ('U8', Uint8),
        ('U64', Uint64),
        ('U128', Uint128),
        ('ByteArray', bytes),
        ('Address', Address),
        ('Container', ContainerRefCell),
        ('ContainerRef', 'move_vm.types.values.ContainerRef'),
        ('IndexedRef', 'move_vm.types.values.IndexedRef')
    ]




    def is_valid_script_arg(self, sig: SignatureToken) -> bool:
        if sig.tag == SerializedType.U8:
            return self.U8
        elif sig.tag == SerializedType.U64:
            return self.U64
        elif sig.tag == SerializedType.U128:
            return self.U128
        elif sig.tag == SerializedType.BOOL:
            return self.Bool
        elif sig.tag == SerializedType.ADDRESS:
            return self.Address
        elif sig.tag == SerializedType.BYTEARRAY:
            return self.ByteArray
        elif sig == VectorU8:
            return self.Container and self.value.v0.U8
        else:
            return False

    @classmethod
    def Uint8(cls, x: Uint8) -> ValueImpl:
        return ValueImpl('U8', x)

    @classmethod
    def Uint64(cls, x: Uint64) -> ValueImpl:
        return ValueImpl('U64', x)

    @classmethod
    def Uint128(cls, x: Uint128) -> ValueImpl:
        return ValueImpl('U128', x)

    @classmethod
    def bool(cls, x: bool) -> ValueImpl:
        return ValueImpl('Bool', x)

    @classmethod
    def byte_array(cls, x: ByteArray) -> ValueImpl:
        return ValueImpl('ByteArray', x)

    @classmethod
    def vector_u8(cls, x: bytes) -> ValueImpl:
        return ValueImpl.new_container(Container('U8', bytearray(x)))


    @classmethod
    def address(cls, x: Address) -> ValueImpl:
        return ValueImpl('Address', x)

    @classmethod
    def struct_(cls, s: Struct) -> ValueImpl:
        return ValueImpl.new_container(s.v0)


    @classmethod
    def new_container(cls, container: Container) -> ValueImpl:
        return cls('Container', ContainerRefCell(container))

    def value_ref(self, ty):
        if not self.is_primitive():
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR))
        if self.value_type == ty:
            return self.value
        else:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                "cannot take {} as &{}",
                self.value_type, ty
                ))
            raise VMException(status)

    def as_value_ref(self, ty):
        return self.value_ref(ty)

    def is_primitive(self) -> bool:
        if self.enum_name in ['Bool', 'U8', 'U64', 'U128', 'ByteArray', 'Address']:
            return True
        else:
            return False

    #Implementation of Move copy.
    def copy_value(self) -> ValueImpl:
        if self.is_primitive():
            return ValueImpl(self.enum_name, self.value)
        elif self.Invalid:
            return ValueInvalid
        elif self.enum_name in ['ContainerRef', 'IndexedRef']:
            return ValueImpl(self.enum_name, self.value.copy_value())
        elif self.Container:
            container = self.value.borrow().v0.copy_value()
            return ValueImpl('Container', ContainerRefCell(container))
        else:
            bail("unreachable!")


    #Equality tests of Move values. Errors are raised when types mismatch.
    #It is intented to NOT use or even implement the standard library traits Eq
    def equals(self, other) -> bool:
        if type(self) != type(other):
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR))
        if self.value_type != other.value_type:
            breakpoint()
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                "cannot compare values: {}, {}", self.value_type, other.value_type))
            raise VMException(status)
        if self.is_primitive():
            return self.value == other.value
        elif self.Container:
            return self.value.borrow().v0.equals(other.value.borrow().v0)
        else:
            return self.value.equals(other.value)

    def cast(self, ty):
        #TTODO: cast to vec<u8> or bytes ?
        if self.is_primitive() and self.value_type == ty:
            return self.value
        elif ty == ContainerRef and self.value_type == ty:
            return self.value
        elif ty == IndexedRef and self.value_type == ty:
            return self.value
        elif ty == IntegerValue:
            if self.value_type in [Uint8, Uint64, Uint128]:
                return IntegerValue(self.enum_name, self.value)
            else:
                raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR)\
                        .with_message(format_str("cannot cast {} to integer", self)))
        elif ty == Reference:
            if self.ContainerRef:
                return ReferenceImpl('ContainerRef', self.value)
            elif self.IndexedRef:
                return ReferenceImpl('IndexedRef', self.value)
            else:
                raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR)\
                    .with_message(format_str("cannot cast {:?} to reference", v)))
        elif ty == Container:
            if self.Container:
                return take_unique_ownership(self.value)
            else:
                raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR)\
                    .with_message(format_str("cannot cast {:?} to container", v,)))
        elif ty == Struct:
            if self.Container:
                return Struct(take_unique_ownership(self.value))
            else:
                raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR)\
                    .with_message(format_str("cannot cast {:?} to struct", v,)))
        elif ty == StructRef:
            ref = self.cast(ContainerRef)
            return StructRef(ref.enum_name, ref.value)
        elif isinstance(ty, BytesT):
            if self.Container and self.value.v0.U8:
                return bytes(self.value.v0.value)
            else:
                raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR)\
                    .with_message(format_str("cannot cast {:?} to vector<u8>", v,)))
        else:
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                            "cannot cast {} to {}",
                            self.value,
                            ty
                        )))


    def value_as(self, ty):
        return self.cast(ty)

    def size(self) -> AbstractMemorySize:
        if self.enum_name in ('Invalid', 'U8', 'U64', 'U128', 'Bool'):
            return CONST_SIZE
        elif self.Address:
            return AbstractMemorySize.new(ADDRESS_LENGTH)
        elif self.ByteArray:
            return AbstractMemorySize.new(self.value.__len__())
        elif self.ContainerRef:
            return self.value.size()
        elif self.IndexedRef:
            return self.value.size()
        elif self.Container:
            # TODO: in case the borrow fails the VM will panic.
            return self.value.borrow().v0.size()
        else:
            bail("unreachable!")

    @classmethod
    def simple_deserialize(cls, blob: bytes, layout: Type) -> Value:
        cursor = Cursor(blob)
        try:
            ret = cls.simple_decode(cursor, layout)
            if not cursor.is_finished():
                raise IOError("bytes not all consumed:{}, {}".format(
                    len(blob), cursor.offset))
        except Exception as err:
            # traceback.print_exc()
            # breakpoint()
            raise VMException(VMStatus(StatusCode.INVALID_DATA).with_message(err))

        return ret

    @classmethod
    def simple_decode(cls, cursor, layout) -> Value:
        if layout.Bool:
            return Value.bool(BoolT.decode(cursor))
        elif layout.U8:
            return Value.Uint8(Uint8.decode(cursor))
        elif layout.U64:
            return Value.Uint64(Uint64.decode(cursor))
        elif layout.U128:
            return Value.Uint128(Uint128.decode(cursor))
        elif layout.ByteArray:
            return Value.vector_u8(BytesT().decode(cursor))
        elif layout.Address:
            return Value.address(Address.decode(cursor))

        elif layout.Struct:
            fds = layout.value.value.field_definitions
            fields = []
            for fd in fds:
                field = cls.simple_decode(cursor, fd)
                fields.append(field)
            return Value.struct_(Struct.pack(fields))

        elif layout.Vector:
            size = Uint32.decode(cursor)
            if layout.value.enum_name == 'U8':
                return ValueImpl.vector_u8(cursor.read_bytes(size))

            arr = []
            for _i in range(size):
                arr.append(ValueImpl.simple_decode(cursor, layout.value))

            if layout.value.enum_name in ['U64', 'U128', 'Bool']:
                arr = [x.value for x in arr]
                return ValueImpl.new_container(Container(layout.value.enum_name, arr))
            else:
                return ValueImpl.new_container(Container('General', arr))
        else:
            bail("unreachable!")

    @classmethod
    def gas_costtable_to_value(cls, cost_table: CostTable) -> Value:
        def gas_cost_to_container(cost: GasCost):
            #Container(RefCell { value: General([U64(27), U64(1)]) })
            container = Container('General', [
                    ValueImpl.Uint64(cost.instruction_gas.v0),
                    ValueImpl.Uint64(cost.memory_gas.v0),
                ])
            return ValueImpl.new_container(container)

        instruction_table = [gas_cost_to_container(x) for x in cost_table.instruction_table]
        native_table = [gas_cost_to_container(x) for x in cost_table.native_table]
        instruction_v = ValueImpl.new_container(Container('General', instruction_table))
        native_v = ValueImpl.new_container(Container('General', native_table))
        return ValueImpl.new_container(Container('General',[instruction_v, native_v]))

    def simple_serialize(self, layout: Type) -> bytes:
        if self.is_primitive() and layout.enum_name == self.enum_name:
            return self.value_type.encode(self.value)
        elif self.Container and layout.Struct:
            container = self.value.borrow().v0
            struct_def = layout.value
            return container.simple_serialize(struct_def)
        elif self.Container and layout.Vector:
            container = self.value.borrow().v0
            ty = layout.value
            return container.simple_serialize_vector(ty)
        else:
            raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
                    .with_message(format_str("cannot serialize value {} as {}", self, layout))
                )




ValueInvalid = ValueImpl('Invalid')

# A container is a collection of values. It is used to represent data structures like a
# Move vector or struct.
#
# There is one general container that can be used to store an array of any values, same
# type or not, and a few specialized flavors to offer compact memory layout for small
# primitive types.
#
# Except when not owned by the VM stack, a container always lives inside an Rc<RefCell<>>,
# making it possible to be shared by references.
class Container(RustEnum):
    _enums = [
        ('General', [ValueImpl]),
        ('U8', bytearray),
        ('U64', [Uint64]),
        ('U128', [Uint128]),
        ('Bool', [bool])
    ]

    def __len__(self) -> usize:
        return self.value.__len__()

    def copy_value(self) -> Container:
        if self.General:
            arr = [x.copy_value() for x in self.value]
            return Container('General', arr)
        else:
            return deepcopy(self)


    def equals(self, other) -> bool:
        if type(self) != type(other):
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR))
        if self.value_type != other.value_type:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                "cannot compare container values: {}, {}", self.value_type, other.value_type))
            raise VMException(status)
        if not self.General:
            return self.value == other.value
        else:
            if len(self.value) != len(other.value):
                return False
            for (v1, v2) in zip(self.value, other.value):
                if not v1.equals(v2):
                    return False
            return True

    def size(self) -> AbstractMemorySize:
        if self.U8:
            return AbstractMemorySize.new(self.__len__() * 1)
        elif self.U64:
            return AbstractMemorySize.new(self.__len__() * 8)
        elif self.U128:
            return AbstractMemorySize.new(self.__len__() * 16)
        if self.Bool:
            return AbstractMemorySize.new(self.__len__() * 1)
        elif self.General:
            ret = STRUCT_SIZE
            for v in self.value:
                ret = ret.map2(v.size(), add_lambda)
            return ret
        else:
            bail("unreachable!")

    def simple_serialize(self, struct_def: StructDef) -> bytes:
        v = self.value
        if type(struct_def) == StructDef:
            if struct_def.Struct and self.General:
                inner = struct_def.value
                if len(v) == len(inner.field_definitions):
                    ret = bytearray()
                    # ret.extend(serialize_tuple(len(v))) #serialize_tuple do nothing
                    for (layout, val) in zip(inner.field_definitions, v):
                        ret.extend(val.simple_serialize(layout))
                    return bytes(ret)

        raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
            .with_message(format_str("cannot serialize container value {} as {}", self, struct_def))
        )

    def simple_serialize_vector(self, ty: Type) -> bytes:
        if self.General:
            v = self.value
            ret = bytearray()
            ret.extend(Uint32.encode(len(v)))
            for val in v:
                ret.extend(val.simple_serialize(ty))
            return bytes(ret)
        elif self.enum_name in ['U8', 'U64', 'U128', 'Bool'] and ty.enum_name == self.enum_name:
            return self.value_type.encode(self.value)

        raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
            .with_message(format_str("cannot serialize container value {} as {}", self, struct_def))
        )



# Status for global (on-chain) data:
# Clean - the data was only read.
# Dirty - the data was possibly modified.
class GlobalDataStatus(RustEnum):
    _enums = [
        ('Clean', None),
        ('Dirty', None)
    ]

GlobalDataStatus_Clean = GlobalDataStatus('Clean')
GlobalDataStatus_Dirty = GlobalDataStatus('Dirty')


class GlobalDataStatusRefCell(RefCellCanoser):
    delegate_type = GlobalDataStatus


# A ContainerRef is a direct reference to a container, which could live either in the frame
# or in global storage. In the latter case, it also keeps a status flag indicating whether
# the container has been possibly modified.
class ContainerRef(RustEnum):
    _enums = [
        ('Local', ContainerRefCell),
        ('Global', 'move_vm.types.values.GlobalValue')
    ]

    def borrow(self) -> Ref:
        if self.Local:
            return self.value.borrow()
        else:
            return self.value.container.borrow()

    def borrow_mut(self) -> RefMut:
        if self.Local:
            return self.value.borrow_mut()
        else:
            self.value.status.borrow_mut_set(GlobalDataStatus_Dirty)
            return self.value.container.borrow_mut()

    def copy_value(self) -> ContainerRef:
        if self.Local:
            return ContainerRef('Local', self.value)
        else:
            return ContainerRef('Global', self.value)

    def equals(self, other) -> bool:
        return self.borrow().v0.equals(other.borrow().v0)

    #Implementation of the Move operation read ref.
    def read_ref(self) -> Value:
        return ValueImpl.new_container(self.borrow().v0.copy_value())

    #Implementation of the Move operation write ref.
    def write_ref(self, v: Value) -> None:
        if v.Container:
            refmut = self.borrow_mut()
            refmut.cell.v0 = take_unique_ownership(v.value)
        else:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                        "cannot write value {} to container ref {}",
                        v, self
                    ))
            raise VMException(status)


    def borrow_elem(self, idx: usize) -> ValueImpl:
        r = self.borrow().v0
        if idx >= r.__len__():
            raise VMException(
                VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR).with_message(format_str(
                    "index out of bounds when borrowing container element: got: {}, len: {}",
                    idx,
                    r.__len__()
                ))
            )

        if r.General:
            vv = r.value[idx]
            if vv.Container:
                if self.Local:
                    r = ContainerRef('Local', vv.value)
                else:
                    r = ContainerRef('Global', GlobalValue(self.value.status, vv.value))
                return ValueImpl('ContainerRef', r)
            else:
                return ValueImpl('IndexedRef', IndexedRef(
                    idx,
                    self.copy_value(),
                ))
        else:
            return ValueImpl('IndexedRef', IndexedRef(
                idx,
                self.copy_value(),
            ))

    def size(self) -> AbstractMemorySize:
        return words_in(REFERENCE_SIZE)


# A Move reference pointing to an element in a container.
class IndexedRef(CanoserStruct):
    _fields = [
        ('idx', usize),
        ('container_ref', ContainerRef)
    ]

    def copy_value(self) -> IndexedRef:
        return IndexedRef(self.idx, self.container_ref.copy_value())

    def equals(self, other) -> bool:
        if type(self) != type(other):
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR))
        c1 = self.container_ref.borrow().v0
        c2 = other.container_ref.borrow().v0
        if c1.value_type == c2.value_type:
            if c1.General:
                return c1.value[self.idx].equals(c2.value[other.idx])
            else:
                return c1.value[self.idx] == c2.value[other.idx]
        if c1.General:
            return c1.value[self.idx].as_value_ref(c2.value_type.atype) == c2.value[other.idx]
        elif c2.General:
            return c1.value[self.idx] == c2.value[other.idx].as_value_ref(c1.value_type.atype)
        else:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                "cannot compare references: {}, {}", self.value_type, other.value_type))
            raise VMException(status)

    def read_ref(self) -> Value:
        container = self.container_ref.borrow().v0
        value = container.value[self.idx]
        if container.General:
            return value.copy_value()
        elif container.U8:
            return ValueImpl('U8', value)
        elif container.U64:
            return ValueImpl('U64', value)
        elif container.U128:
            return ValueImpl('U128', value)
        elif container.Bool:
            return ValueImpl('Bool', value)
        else:
            bail("unreachable!")


    def write_ref(self, x: Value) -> None:
        if not x.is_primitive():
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                        "cannot write value {} to indexed ref {}",
                        x, self
                    ))
            raise VMException(status)
        container = self.container_ref.borrow_mut().v0
        if container.General:
            container.value[self.idx] = x
        elif container.U8 and x.U8:
            container.value[self.idx] = x.value
        elif container.U64 and x.U64:
            container.value[self.idx] = x.value
        elif container.U128 and x.U128:
            container.value[self.idx] = x.value
        elif container.Bool and x.Bool:
            container.value[self.idx] = x.value
        else:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                        "cannot write value {} to indexed ref {}",
                        x, self
                    ))
            raise VMException(status)

    def size(self) -> AbstractMemorySize:
        return words_in(REFERENCE_SIZE)

# An umbrella enum for references. It is used to hide the internals of the public type
# Reference.
class ReferenceImpl(RustEnum):
    _enums = [
        ('IndexedRef', IndexedRef),
        ('ContainerRef', ContainerRef)
    ]

    def read_ref(self) -> Value:
        return self.value.read_ref()

    def write_ref(self, x: Value) -> None:
        self.value.write_ref(x)

    def size(self) -> AbstractMemorySize:
        return self.value.size()


"""
/***************************************************************************************
 *
 * Public Types
 *
 *   Types visible from outside the module. They are almost exclusively wrappers around
 *   the internal representation, acting as public interfaces. The methods they provide
 *   closely resemble the Move concepts their names suggest: move_local, borrow_field,
 *   pack, unpack, etc.
 *
 *   They are opaque to an external caller by design -- no knowledge about the internal
 *   representation is given and they can only be manipulated via the public methods,
 *   which is to ensure no arbitratry invalid states can be created unless some crucial
 *   internal invariants are violated.
 *
 **************************************************************************************/
"""

# A reference to a Move struct that allows you to take a reference to one of its fields.
class StructRef(ContainerRef):
    def borrow_field(self, idx: usize) -> Value:
        return self.borrow_elem(idx)


# A generic Move reference that offers two functinalities: read_ref & write_ref.
Reference = ReferenceImpl


# A Move value -- a wrapper around `ValueImpl` which can be created only through valid
# means.
Value = ValueImpl

# The locals for a function frame. It allows values to be read, written or taken
# reference from.
class Locals(ContainerRefCell):

    def borrow_loc(self, idx: usize) -> Value:
        r = self.borrow().v0
        if idx >= r.__len__():
            raise VMException(
                VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR).with_message(format_str(
                    "index out of bounds when borrowing local: got: {}, len: {}",
                    idx,
                    r.__len__()
                )),
            )

        if r.General:
            v = r.value
            if v[idx].Container:
                return ValueImpl('ContainerRef', ContainerRef('Local', v[idx].value))
            elif v[idx].is_primitive():
                return ValueImpl('IndexedRef',IndexedRef(idx, ContainerRef('Local', self)))
            else:
                raise VMException(VMStatus(
                    StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR).with_message(format_str(
                        "cannot borrow local {}", v[idx])))
        else:
            raise VMException(VMStatus(
                StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR).with_message(format_str(
                    "bad container for locals: {}", r.value)))

    @classmethod
    def new(cls, n: usize) -> Locals:
        container = Container('General', [ValueInvalid for _x in range(n)])
        return cls(container)

    def copy_loc(self, idx: usize) -> Value:
        r = self.borrow().v0
        if r.General:
            v = r.value
        else:
            bail("unreachable!")

        try:
            value = v[idx]
            if value.Invalid:
                raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR).with_message(
                    format_str("cannot copy invalid value at index {}", idx)))
            else:
                return value.copy_value()
        except IndexError:
            status = VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION).with_message(format_str(
                    "local index out of bounds: got {}, len: {}",
                    idx,
                    v.__len__()
                ))
            raise VMException(status)


    def swap_loc(self, idx: usize, x: Value) -> Value:
        r = self.borrow_mut().v0
        if r.General:
            v = r.value
        else:
            bail("unreachable!")

        try:
            value = v[idx]
            if value.Container:
                referrers = gc.get_referrers(value.value)
                length = len(referrers)
                if length > 1:
                    #TTODO: how to get strong_count of value
                    count = [x['value'] for x in referrers if 'value' in x].count(value.value)
                    logger.warning(f"moving container with dangling references:{value.value.v0}")
                    logger.warning(f"get_referrers:{length}, self:{count}")
                    if length > count:
                        raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
                            .with_message("moving container with dangling references"))
            v[idx] = x
            return value
        except IndexError:
            status = VMStatus(StatusCode.VERIFIER_INVARIANT_VIOLATION).with_message(format_str(
                    "local index out of bounds: got {}, len: {}",
                    idx,
                    v.__len__()
                ))
            raise VMException(status)


    def move_loc(self, idx: usize) -> Value:
        value = self.swap_loc(idx, ValueInvalid)
        if value.Invalid:
            raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
                .with_message(format_str("cannot move invalid value at index {}", idx)))
        else:
            return value

    def store_loc(self, idx: usize, x: Value) -> None:
        self.swap_loc(idx, x)


# An integer value in Move.
class IntegerValue(RustEnum):
    _enums = [
        ('U8', Uint8),
        ('U64', Uint64),
        ('U128', Uint128),
    ]

    def value_as(self, ty):
        return self.cast(ty)

    def check_other_type(self, other: IntegerValue):
        if type(self) != type(other):
            raise VMException(VMStatus(StatusCode.INTERNAL_TYPE_ERROR))
        if self.value_type != other.value_type:
            status = VMStatus(StatusCode.INTERNAL_TYPE_ERROR).with_message(format_str(
                "cannot compute values: {}, {}", self.value_type, other.value_type))
            raise VMException(status)


    def add_checked(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value+other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def sub_checked(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value-other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def mul_checked(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value*other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def div_checked(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value // other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def rem_checked(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value % other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def bit_or(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value | other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def bit_and(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value & other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def bit_xor(self, other: IntegerValue) -> IntegerValue:
        self.check_other_type(other)
        try:
            return IntegerValue(self.enum_name, self.value ^ other.value)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))



    def shl_checked(self, n_bits: Uint8) -> IntegerValue:
        if n_bits >= self.value_type.byte_lens * 8:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))
        try:
            return IntegerValue(self.enum_name, (self.value << n_bits) % (self.value_type.max_value+1))
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def shr_checked(self, n_bits: Uint8) -> IntegerValue:
        if n_bits >= self.value_type.byte_lens * 8:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))
        try:
            return IntegerValue(self.enum_name, self.value >> n_bits)
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def lt(self, other: IntegerValue) -> bool:
        self.check_other_type(other)
        try:
            return self.value < other.value
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def le(self, other: IntegerValue) -> bool:
        self.check_other_type(other)
        try:
            return self.value <= other.value
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def gt(self, other: IntegerValue) -> bool:
        self.check_other_type(other)
        try:
            return self.value > other.value
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def ge(self, other: IntegerValue) -> bool:
        self.check_other_type(other)
        try:
            return self.value >= other.value
        except Exception:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR))

    def into_value(self) -> Value:
        return Value(self.enum_name, self.value)

    def into(self, ty) -> int:
        return self.value % (ty.max_value+1)

    def cast(self, ty) -> int:
        if self.value_type == ty:
            return self.value
        elif self.value <= ty.max_value:
            return self.value
        else:
            raise VMException(VMStatus(StatusCode.ARITHMETIC_ERROR)\
                .with_message(format_str("cannot cast {} to {}", self.value_type, ty)))


# A Move struct.
class Struct(CanoserStruct):
    _fields = [('v0', Container)]

    def size(self) -> AbstractMemorySize:
        return self.v0.size()

    @classmethod
    def pack(cls, vals) -> Struct:
        return cls(Container('General', vals))


    def unpack(self) -> List[Value]:
        if self.v0.General:
            return self.v0.value
        else:
            raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
                                .with_message("not a struct"))

    def simple_serialize(self, layout: StructDef) -> bytes:
        return self.v0.simple_serialize(layout)


# A special value that lives in global storage.
#
# Callers are allowed to take global references from a `GlobalValue`. A global value also contains
# an internal flag, indicating whether the value has potentially been modified or not.
#
# For any given value in storage, only one `GlobalValue` may exist to represent it at any time.
# This means that:
# * `GlobalValue` **does not** and **cannot** implement `Clone`!
# * a borrowed reference through `borrow_global` is represented through a `&GlobalValue`.
# * `borrow_global_mut` is also represented through a `&GlobalValue` -- the bytecode verifier
#   enforces mutability restrictions.
# * `move_from` is represented through an owned `GlobalValue`.
class GlobalValue(CanoserStruct):
    _fields = [
        ('status', GlobalDataStatusRefCell),
        ('container', ContainerRefCell)
    ]

    def size(self) -> AbstractMemorySize:
        # TODO: should it be self.container.borrow().size()
        return words_in(REFERENCE_SIZE)

    @classmethod
    def new(cls, v: Value) -> GlobalValue:
        if v.Container:
            return GlobalValue(GlobalDataStatusRefCell(GlobalDataStatus_Clean), v.value)
        else:
            raise VMException(VMStatus(StatusCode.UNKNOWN_INVARIANT_VIOLATION_ERROR)\
                .with_message(format_str("cannot create global ref from {}", v)))

    def borrow_global(self) -> Value:
        return ValueImpl('ContainerRef', ContainerRef('Global', self))


    def mark_dirty(self) -> None:
        self.status.borrow_mut_set(GlobalDataStatus_Dirty)

    def is_clean(self) -> bool:
        return self.status.borrow().v0 == GlobalDataStatus_Clean

    def is_dirty(self) -> bool:
        return self.status.borrow().v0 == GlobalDataStatus_Dirty

    def into_owned_struct(self) -> Struct:
        return Struct(take_unique_ownership(self.container))



"""
/***************************************************************************************
 *
 * Borrows (Internal)
 *
 *   Helper functions to handle Rust borrows. When borrowing from a RefCell, we want
 *   to return an error instead of panicking.
 *
 **************************************************************************************/
"""
def take_unique_ownership(r: RefCell):
    return r.into_inner()



"""
/***************************************************************************************
 *
 * Serialization & Deserialization
 *
 *   LCS implementation for VM values. Note although values are represented as Rust
 *   enums that carry type info in the tags, we should NOT rely on them for
 *   serialization:
 *     1) Depending on the specific internal representation, it may be impossible to
 *        reconstruct the layout from a value. For example, one cannot tell if a general
 *        container is a struct or a value.
 *     2) Even if 1) is not a problem at a certain time, we may change to a different
 *        internal representation that breaks the 1-1 mapping. Extremely speaking, if
 *        we switch to untagged unions one day, none of the type info will be carried
 *        by the value.
 *
 *   Therefore the appropriate & robust way to implement serialization & deserialization
 *   is to involve an explicit representation of the type layout.
 *
 **************************************************************************************/
"""
