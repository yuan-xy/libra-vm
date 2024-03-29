from mol.vm.file_format_common import *
from libra.rustlib import *
import pytest

def test_from_u8():
    assert Opcodes.from_u8(3) == Opcodes.BR_TRUE
    assert Opcodes.from_u8(59) == Opcodes.CAST_U128
    with pytest.raises(Exception):
        Opcodes.from_u8(60)
    with pytest.raises(Exception):
        Opcodes.from_u8(0)

def test_binary_len():
    binary_data = BinaryData()
    for _ in range(100):
        binary_data.push(1)
    assert_equal(binary_data.__len__(), 100)
    assert binary_data._binary == bytearray(b'\x01'*100)



def test_vec_to_binary():
    vecs = [[], [0], [1, 2], [255]*99999]
    for vec in vecs:
        binary_data = BinaryData(vec)
        vec2 = binary_data.into_inner()
        assert_equal(vec.__len__(), vec2.__len__())


def test_binary_push():
    items = [0, 100, 255]
    for item in items:
        binary_data = BinaryData()
        binary_data.push(item)
        assert_equal(binary_data.into_inner()[0], item)


def test_binary_extend():
    vecs = [[], [0], [1, 2], [255]*99999]
    for vec in vecs:
        binary_data = BinaryData()
        binary_data.extend(vec)
        assert_equal(binary_data.__len__(), vec.__len__())
        for (index, item) in enumerate(vec):
            assert_equal(item, binary_data.as_inner()[index])

