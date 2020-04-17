from libra.rustlib import bail, usize, snake_to_camel
from libra.vm_error import VMStatus, StatusCode
from canoser import Cursor, Uint8, Uint32, Uint16, Uint64, Uint128
from enum import IntEnum, unique
from dataclasses import dataclass, field
from typing import List, Optional
from vm.vm_exception import VMException

# Constants for the binary format.
#
# Definition for the constants of the binary format, used by the serializer and the deserializer.
# This module also offers helpers for the serialization and deserialization of certain
# integer indexes.
#
# We use LEB128 for integer compression. LEB128 is a representation from the DWARF3 spec,
# http://dwarfstd.org/Dwarf3Std.php or https://en.wikipedia.org/wiki/LEB128.
# It's used to compress mostly indexes into the main binary tables.


# Constant values for the binary format header.
#
# The binary header is magic +  version info + table count.
class BinaryConstants:

    # The blob that must start a binary.
    LIBRA_MAGIC_SIZE: usize = 4
    LIBRA_MAGIC = bytes([0xA1, 0x1C, 0xEB, 0x0B])
    # The `LIBRA_MAGIC` size, 1 byte for major version, 1 byte for minor version and 1 byte
    # for table count.
    HEADER_SIZE: usize = LIBRA_MAGIC_SIZE + 3
    # A (Table Type, Start Offset, Byte Count) size, which is 1 byte for the type and
    # 4 bytes for the offset/count.
    TABLE_HEADER_SIZE: Uint32 = 4 * 2 + 1


# Constants for table types in the binary.
#
# The binary contains a subset of those tables. A table specification is a tuple (table type,
# start offset, byte count) for a given table.
#[repr(Uint8)]
class TableType(IntEnum):
    MODULE_HANDLES          = 0x1
    STRUCT_HANDLES          = 0x2
    FUNCTION_HANDLES        = 0x3
    ADDRESS_POOL            = 0x4
    IDENTIFIERS             = 0x5
    BYTE_ARRAY_POOL         = 0x6
    MAIN                    = 0x7
    STRUCT_DEFS             = 0x8
    FIELD_DEFS              = 0x9
    FUNCTION_DEFS           = 0xA
    TYPE_SIGNATURES         = 0xB
    FUNCTION_SIGNATURES     = 0xC
    LOCALS_SIGNATURES       = 0xD

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_TABLE_TYPE))
        return cls(u8)


# Constants for signature kinds (type, function, locals). Those values start a signature blob.
class SignatureType(IntEnum):
    TYPE_SIGNATURE          = 0x1
    FUNCTION_SIGNATURE      = 0x2
    LOCAL_SIGNATURE         = 0x3

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_SIGNATURE_TYPE))
        return cls(u8)


# Constants for signature blob values.
class SerializedType(IntEnum):
    BOOL                    = 0x1
    U8                      = 0x2
    U64                     = 0x3
    U128                    = 0x4
    ADDRESS                 = 0x5
    REFERENCE               = 0x6
    MUTABLE_REFERENCE       = 0x7
    STRUCT                  = 0x8
    TYPE_PARAMETER          = 0x9
    VECTOR                  = 0xA

    @property
    def tagname(self):
        return snake_to_camel(self.name)

    def is_primitive(self) -> bool:
        if self in [SerializedType.BOOL, SerializedType.U8, SerializedType.U64, SerializedType.U128, SerializedType.ADDRESS]:
            return True
        else:
            return False

    def is_integer(self) -> bool:
        if self in [SerializedType.U8, SerializedType.U64, SerializedType.U128]:
            return True
        else:
            return False


    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_SERIALIZED_TYPE))
        return cls(u8)



class SerializedNominalResourceFlag(IntEnum):
    NOMINAL_RESOURCE        = 0x1,
    NORMAL_STRUCT           = 0x2,

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_SERIALIZED_TYPE))
        return cls(u8)



class SerializedKind(IntEnum):
    ALL                     = 0x1,
    UNRESTRICTED            = 0x2,
    RESOURCE                = 0x3,

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_SERIALIZED_TYPE))
        return cls(u8)



class SerializedNativeStructFlag(IntEnum):
    NATIVE                  = 0x1,
    DECLARED                = 0x2,

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_SERIALIZED_TYPE))
        return cls(u8)



# List of opcodes constants.
@unique
class Opcodes(IntEnum):
    POP                     = 0x01,
    RET                     = 0x02,
    BR_TRUE                 = 0x03,
    BR_FALSE                = 0x04,
    BRANCH                  = 0x05,
    LD_U64                  = 0x06,
    LD_ADDR                 = 0x07,
    LD_TRUE                 = 0x08,
    LD_FALSE                = 0x09,
    COPY_LOC                = 0x0A,
    MOVE_LOC                = 0x0B,
    ST_LOC                  = 0x0C,
    MUT_BORROW_LOC          = 0x0D,
    IMM_BORROW_LOC          = 0x0E,
    MUT_BORROW_FIELD        = 0x0F,
    IMM_BORROW_FIELD        = 0x10,
    LD_BYTEARRAY            = 0x11,
    CALL                    = 0x12,
    PACK                    = 0x13,
    UNPACK                  = 0x14,
    READ_REF                = 0x15,
    WRITE_REF               = 0x16,
    ADD                     = 0x17,
    SUB                     = 0x18,
    MUL                     = 0x19,
    MOD                     = 0x1A,
    DIV                     = 0x1B,
    BIT_OR                  = 0x1C,
    BIT_AND                 = 0x1D,
    XOR                     = 0x1E,
    OR                      = 0x1F,
    AND                     = 0x20,
    NOT                     = 0x21,
    EQ                      = 0x22,
    NEQ                     = 0x23,
    LT                      = 0x24,
    GT                      = 0x25,
    LE                      = 0x26,
    GE                      = 0x27,
    ABORT                   = 0x28,
    GET_TXN_GAS_UNIT_PRICE  = 0x29,
    GET_TXN_MAX_GAS_UNITS   = 0x2A,
    GET_GAS_REMAINING       = 0x2B,
    GET_TXN_SENDER          = 0x2C,
    EXISTS                  = 0x2D,
    MUT_BORROW_GLOBAL       = 0x2E,
    IMM_BORROW_GLOBAL       = 0x2F,
    MOVE_FROM               = 0x30,
    MOVE_TO                 = 0x31,
    GET_TXN_SEQUENCE_NUMBER = 0x32,
    GET_TXN_PUBLIC_KEY      = 0x33,
    FREEZE_REF              = 0x34,
    # TODO: reshuffle once file format stabilizes
    SHL                     = 0x35,
    SHR                     = 0x36,
    LD_U8                   = 0x37,
    LD_U128                 = 0x38,
    CAST_U8                 = 0x39,
    CAST_U64                = 0x3A,
    CAST_U128               = 0x3B,

    @property
    def tagname(self):
        return snake_to_camel(self.name)

    @classmethod
    def from_u8(cls, u8):
        if u8 <=0 or u8 > len(cls):
            raise VMException(VMStatus(StatusCode.UNKNOWN_OPCODE))
        return cls(u8)


# Upper limit on the binary size
BINARY_SIZE_LIMIT: usize = usize.max_value

# A wrapper for the binary vector
@dataclass
class BinaryData:
    _binary: bytearray = field(default_factory=bytearray)


    def as_inner(self) -> bytearray:
        return self._binary


    def into_inner(self) -> bytearray:
        return self._binary


    def push(self, item: Uint8) -> None:
        if self._binary.__len__() < usize.max_value:
            self._binary.append(item)
        else:
            bail(
                "binary size ({}) + 1 is greater than limit ({})",
                self._binary.__len__(),
                BINARY_SIZE_LIMIT,
            )


    def extend(self, vec: bytearray) -> None:
        vec_len: usize = vec.__len__()
        if self.__len__() + vec_len <= usize.max_value:
            self._binary.extend(vec)
        else:
            bail(
                "binary size ({}) + {} is greater than limit ({})",
                self.__len__(),
                vec.__len__(),
                BINARY_SIZE_LIMIT,
            )


    def __len__(self) -> usize:
        return self._binary.__len__()


    def is_empty(self) -> bool:
        return bool(self._binary)


    def clear(self):
        self._binary.clear()



# Take a `bytearray` and a value to write to that vector and applies LEB128 logic to
# compress the Uint16.
def write_Uint16_as_uleb128(binary: BinaryData, value: Uint16) -> None:
    write_Uint32_as_uleb128(binary, value)


# Take a `bytearray` and a value to write to that vector and applies LEB128 logic to
# compress the Uint32.
def write_Uint32_as_uleb128(binary: BinaryData, value: Uint32) -> None:
    Uint32.check_value(value)
    val = value
    while True:
        v: Uint8 = (val & 0x7f)
        if v != val:
            binary.push(v | 0x80)
            val >>= 7
        else:
            binary.push(v)
            break



# Write a `Uint16` in Little Endian format.
def write_Uint16(binary: BinaryData, value: Uint16) -> None:
    binary.extend(value.to_bytes(2, byteorder="little", signed=False))


# Write a `Uint32` in Little Endian format.
def write_Uint32(binary: BinaryData, value: Uint32) -> None:
    binary.extend(value.to_bytes(4, byteorder="little", signed=False))


# Write a `Uint64` in Little Endian format.
def write_Uint64(binary: BinaryData, value: Uint64) -> None:
    binary.extend(value.to_bytes(8, byteorder="little", signed=False))


# Write a `Uint128` in Little Endian format.
def write_Uint128(binary: BinaryData, value: Uint128) -> None:
    binary.extend(value.to_bytes(16, byteorder="little", signed=False))


def read_uleb128_as_Uintx(cursor: Cursor, bits: int) -> Uint16:
    if bits == 16:
        max_shift = 14
    elif bits == 32:
        max_shift = 28
    else:
        bail("unsupport bits{bits} for read_uleb128_as_Uintx")
    value = 0
    shift: Uint8 = 0
    while not cursor.is_finished():
        byte = cursor.read_u8()
        val = byte & 0x7f
        value |= (val << shift)
        if val == byte:
            return value
        shift += 7
        if shift > max_shift:
            break
    bail(f"invalid ULEB128 representation for Uint{bits}")


# Reads a `Uint16` in ULEB128 format from a `binary`.
def read_uleb128_as_Uint16(cursor: Cursor) -> Uint16:
    return read_uleb128_as_Uintx(cursor, 16)


# Reads a `Uint32` in ULEB128 format from a `binary`.
#
# Takes a `Cursor<&[Uint8]>` and returns a pair:
#
# Uint32 - value read
#
# Return an error on an invalid representation.
def read_uleb128_as_Uint32(cursor: Cursor) -> Uint32:
    return read_uleb128_as_Uintx(cursor, 32)
