from libra_vm.runtime_types.loaded_data import *

def roundtrip(t: Type):
    ser = t.serialize()
    t2 = Type.deserialize(ser)
    assert t == t2


def test_roundtrip():
    roundtrip(Type('Bool'))
    roundtrip(Type('U8'))
    roundtrip(Type('U64'))
    roundtrip(Type('U128'))
    roundtrip(Type('Address'))
    roundtrip(Type('ByteArray'))

