from move_vm.types.loaded_data import *
from move_vm.types.native_structs import *

def roundtrip(t, clazz = Type):
    ser = t.serialize()
    t2 = clazz.deserialize(ser)
    assert t == t2
    return t2


def test_roundtrip():
    roundtrip(Type('Bool'))
    roundtrip(Type('U8'))
    roundtrip(Type('U64'))
    roundtrip(Type('U128'))
    roundtrip(Type('Address'))
    roundtrip(Type('Vector', Type('U8')))
    definner = StructDefInner([Type('Bool'), Type('U64')])
    struct = Type('Struct', StructDef('Struct', definner))
    roundtrip(struct)
    ref = Type('Reference', struct)
    ref2 = roundtrip(ref)
    assert ref2.value.Struct == True
    assert ref2.value.value == StructDef.new([Type('Bool'), Type('U64')])
    roundtrip(Type('TypeVariable', 12345))
