from libra_vm.file_format_common import *
from libra.rustlib import *
from canoser import Uint8, Uint32, Uint16, Uint64, Uint128, bytes_to_int_list
from typing import List, Optional
import pytest


def test_enum():
    assert TableType.MODULE_HANDLES == 1
    assert Opcodes.RET == 2

# verify all bytes in the vector have the high bit set except the last one
def check_vector(buf: List[Uint8]):
    last_byte: bool = False
    for byte in buf:
        assert (not last_byte)
        if byte & 0x80 == 0:
            last_byte = True
        if not last_byte:
            ensure(byte & 0x80 > 0, "{} & 0x80", byte)

    assert (last_byte)


def tst_Uint16(value: Uint16, expected_bytes: usize):
    buf = BinaryData()
    write_Uint16_as_uleb128(buf, value)
    assert_equal(buf.__len__(), expected_bytes)
    buf = buf.into_inner()
    check_vector(buf)
    val = read_uleb128_as_Uint16(buf)
    assert_equal(value, val)


def tst_Uint32(value: Uint32, expected_bytes: usize):
    buf = BinaryData()
    write_Uint32_as_uleb128(buf, value)
    assert_equal(buf.__len__(), expected_bytes)
    buf = buf.into_inner()
    check_vector(buf)
    val = read_uleb128_as_Uint32(buf)
    assert_equal(value, val)



def test_lab128_Uint16_test():
    tst_Uint16(0, 1)
    tst_Uint16(16, 1)
    tst_Uint16(pow(2, 7) - 1, 1)
    tst_Uint16(pow(2, 7), 2)
    tst_Uint16(pow(2, 7) + 1, 2)
    tst_Uint16(pow(2, 14) - 1, 2)
    tst_Uint16(pow(2, 14), 3)
    tst_Uint16(pow(2, 14) + 1, 3)
    tst_Uint16(Uint16.max_value - 2, 3)
    tst_Uint16(Uint16.max_value - 1, 3)
    tst_Uint16(Uint16.max_value, 3)



def test_lab128_Uint32_test():
    tst_Uint32(0, 1)
    tst_Uint32(16, 1)
    tst_Uint32(pow(2, 7) - 1, 1)
    tst_Uint32(pow(2, 7), 2)
    tst_Uint32(pow(2, 7) + 1, 2)
    tst_Uint32(pow(2, 14) - 1, 2)
    tst_Uint32(pow(2, 14), 3)
    tst_Uint32(pow(2, 14) + 1, 3)
    tst_Uint32(pow(2, 21) - 1, 3)
    tst_Uint32(pow(2, 21), 4)
    tst_Uint32(pow(2, 21) + 1, 4)
    tst_Uint32(pow(2, 28) - 1, 4)
    tst_Uint32(pow(2, 28), 5)
    tst_Uint32(pow(2, 28) + 1, 5)
    tst_Uint32(Uint32.max_value - 2, 5)
    tst_Uint32(Uint32.max_value - 1, 5)
    tst_Uint32(Uint32.max_value, 5)



def test_lab128_malformed_test():
    vecs = [[], [0x80], [0x80, 0x80], [0x80]*4, [0x80, 0x80, 0x80, 0x2]]
    for vec in vecs:
        with pytest.raises(Exception):
            read_uleb128_as_Uint16(vec)

    vecs = [[], [0x80], [0x80, 0x80], [0x80]*4, [0x80, 0x80, 0x80, 0x80, 0x80, 0x2]]
    for vec in vecs:
        with pytest.raises(Exception):
            read_uleb128_as_Uint32(vec)


def uint_roundtrip(value, bytes_len):
    if bytes_len == 2:
        func = write_Uint16
    elif bytes_len == 4:
        func = write_Uint32
    elif bytes_len == 8:
        func = write_Uint64
    else:
        bail("unsupport bytes_len:{}", bytes_len)
    serialized = BinaryData()
    func(serialized, value)
    serialized = serialized.into_inner()
    output = int.from_bytes(serialized, byteorder='little', signed=False)
    assert_equal(value, output)

def test_Uint16_roundtrip():
    uint_roundtrip(0, 2)
    uint_roundtrip(16, 2)
    uint_roundtrip(pow(2, 7) - 1, 2)
    uint_roundtrip(pow(2, 7), 2)
    uint_roundtrip(pow(2, 7) + 1, 2)
    uint_roundtrip(pow(2, 14) - 1, 2)
    uint_roundtrip(pow(2, 14), 2)
    uint_roundtrip(pow(2, 14) + 1, 2)
    uint_roundtrip(Uint16.max_value - 2, 2)
    uint_roundtrip(Uint16.max_value - 1, 2)
    uint_roundtrip(Uint16.max_value, 2)
    with pytest.raises(Exception):
        uint_roundtrip(Uint16.max_value+1, 2)


def test_Uint32_roundtrip():
    uint_roundtrip(0, 4)
    uint_roundtrip(16, 4)
    uint_roundtrip(pow(2, 7) - 1, 4)
    uint_roundtrip(pow(2, 7), 4)
    uint_roundtrip(pow(2, 7) + 1, 4)
    uint_roundtrip(pow(2, 14) - 1, 4)
    uint_roundtrip(pow(2, 14), 4)
    uint_roundtrip(pow(2, 14) + 1, 4)
    uint_roundtrip(pow(2, 21) - 1, 4)
    uint_roundtrip(pow(2, 21), 4)
    uint_roundtrip(pow(2, 21) + 1, 4)
    uint_roundtrip(pow(2, 28) - 1, 4)
    uint_roundtrip(pow(2, 28), 4)
    uint_roundtrip(pow(2, 28) + 1, 4)
    uint_roundtrip(Uint32.max_value - 2, 4)
    uint_roundtrip(Uint32.max_value - 1, 4)
    uint_roundtrip(Uint32.max_value, 4)
    with pytest.raises(Exception):
        uint_roundtrip(Uint32.max_value+1, 4)



def test_Uint64_roundtrip():
    uint_roundtrip(0, 8)
    uint_roundtrip(16, 8)
    uint_roundtrip(pow(2, 7) - 1, 8)
    uint_roundtrip(pow(2, 7), 8)
    uint_roundtrip(pow(2, 7) + 1, 8)
    uint_roundtrip(pow(2, 18) - 1, 8)
    uint_roundtrip(pow(2, 18), 8)
    uint_roundtrip(pow(2, 18) + 1, 8)
    uint_roundtrip(pow(2, 21) - 1, 8)
    uint_roundtrip(pow(2, 21), 8)
    uint_roundtrip(pow(2, 21) + 1, 8)
    uint_roundtrip(pow(2, 56) - 1, 8)
    uint_roundtrip(pow(2, 56), 8)
    uint_roundtrip(pow(2, 56) + 1, 8)
    uint_roundtrip(Uint64.max_value - 2, 8)
    uint_roundtrip(Uint64.max_value - 1, 8)
    uint_roundtrip(Uint64.max_value, 8)
    with pytest.raises(Exception):
        uint_roundtrip(Uint64.max_value+1, 8)

