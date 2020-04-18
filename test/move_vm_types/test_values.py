from mol.move_vm.types.values import *
from mol.vm.errors import *
import pytest

def test_lcls():
    LEN = 4
    lcls = Locals.new(LEN)
    for i in range(LEN):
        with pytest.raises(VMException) as excinfo:
            lcls.copy_loc(i)
        with pytest.raises(VMException) as excinfo:
            lcls.move_loc(i)
        with pytest.raises(VMException) as excinfo:
            lcls.borrow_loc(i)

    lcls.store_loc(1, Value.Uint64(42))

    assert(lcls.copy_loc(1).equals(Value.Uint64(42)))
    r = lcls.borrow_loc(1).value_as(Reference)
    assert(r.read_ref().equals(Value.Uint64(42)))
    assert(lcls.move_loc(1).equals(Value.Uint64(42)))

    with pytest.raises(VMException) as excinfo:
        lcls.copy_loc(1).is_err()
    with pytest.raises(VMException) as excinfo:
        lcls.move_loc(1).is_err()
    with pytest.raises(VMException) as excinfo:
        lcls.borrow_loc(1).is_err()

    with pytest.raises(VMException) as excinfo:
        lcls.copy_loc(LEN + 1).is_err()
    with pytest.raises(VMException) as excinfo:
        lcls.move_loc(LEN + 1).is_err()
    with pytest.raises(VMException) as excinfo:
        lcls.borrow_loc(LEN + 1).is_err()



def test_struct_pack_and_unpack():
    vals = [Value.Uint8(10), Value.Uint64(20), Value.Uint128(30)]
    s = Struct.pack([Value.Uint8(10), Value.Uint64(20), Value.Uint128(30)])
    unpacked = s.unpack()

    assert(vals.__len__() == unpacked.__len__())
    for (v1, v2) in zip(unpacked, vals):
        assert(v1.equals(v2))



def test_struct_borrow_field():
    lcls = Locals.new(1)
    lcls.store_loc(
        0,
        Value.struct_(Struct.pack([Value.Uint8(10), Value.bool(False)])),
    )
    r = lcls.borrow_loc(0).value_as(StructRef)
    print(r)

    def lambda0():
        f = r.borrow_field(1).value_as(Reference)
        assert(f.read_ref().equals(Value.bool(False)))
    lambda0()

    def lambda1():
        f = r.borrow_field(1).value_as(Reference)
        f.write_ref(Value.bool(True))
    lambda1()

    def lambda2():
        f = r.borrow_field(1).value_as(Reference)
        assert(f.read_ref().equals(Value.bool(True)))
    lambda2()




def test_struct_borrow_nested():
    lcls = Locals.new(1)

    def inner(x: Uint64) -> Value:
        return Value.struct_(Struct.pack([Value.Uint64(x)]))

    def outer(x: Uint64) -> Value:
        return Value.struct_(Struct.pack([Value.Uint8(10), inner(x)]))


    lcls.store_loc(0, outer(20))
    r1 = lcls.borrow_loc(0).value_as(StructRef)
    r2 = r1.borrow_field(1).value_as(StructRef)

    def lambda1():
        r3 = r2.borrow_field(0).value_as(Reference)
        assert(r3.read_ref().equals(Value.Uint64(20)))
    lambda1()

    def lambda2():
        r3 = r2.borrow_field(0).value_as(Reference)
        r3.write_ref(Value.Uint64(30))
    lambda2()

    def lambda3():
        r3 = r2.borrow_field(0).value_as(Reference)
        assert(r3.read_ref().equals(Value.Uint64(30)))
    lambda3()

    assert(r2.read_ref().equals(inner(30)))
    assert(r1.read_ref().equals(outer(30)))




def test_global_value_non_struct():
    with pytest.raises(VMException) as excinfo:
        GlobalValue.new(Value.Uint64(100))
    with pytest.raises(VMException) as excinfo:
        GlobalValue.new(Value.bool(False))

    lcls = Locals.new(1)
    lcls.store_loc(0, Value.Uint8(0))
    r = lcls.borrow_loc(0)
    with pytest.raises(VMException) as excinfo:
        GlobalValue.new(r)



def test_global_value():
    gv = GlobalValue.new(Value.struct_(Struct.pack([
        Value.Uint8(100),
        Value.Uint64(200),
    ])))

    def lambda1():
        r = gv.borrow_global().value_as(StructRef)
        f1 = r.borrow_field(0).value_as(Reference)
        f2 = r.borrow_field(1).value_as(Reference)
        assert(f1.read_ref().equals(Value.Uint8(100)))
        assert(f2.read_ref().equals(Value.Uint64(200)))
    lambda1()

    assert(gv.is_clean())

    def lambda2():
        r = gv.borrow_global().value_as(StructRef)
        f1 = r.borrow_field(0).value_as(Reference)
        f1.write_ref(Value.Uint8(222))
    lambda2()

    assert(gv.is_dirty())

    def lambda3():
        r = gv.borrow_global().value_as(StructRef)
        f1 = r.borrow_field(0).value_as(Reference)
        f2 = r.borrow_field(1).value_as(Reference)
        assert(f1.read_ref().equals(Value.Uint8(222)))
        assert(f2.read_ref().equals(Value.Uint64(200)))
    lambda3()




def test_global_value_nested():
    gv: GlobalValue = GlobalValue.new(Value.struct_(Struct.pack([Value.struct_(
        Struct.pack([Value.Uint64(100)]),
    )])))

    def lambda1():
        r1: StructRef = gv.borrow_global().value_as(StructRef)
        r2: StructRef = r1.borrow_field(0).value_as(StructRef)
        r3: Reference = r2.borrow_field(0).value_as(Reference)
        assert(r3.read_ref().equals(Value.Uint64(100)))
    lambda1()

    assert(gv.is_clean())

    def lambda2():
        r1: StructRef = gv.borrow_global().value_as(StructRef)
        r2: StructRef = r1.borrow_field(0).value_as(StructRef)
        r3: Reference = r2.borrow_field(0).value_as(Reference)
        r3.write_ref(Value.Uint64(0))
    lambda2()

    assert(gv.is_dirty())

    def lambda3():
        r1: StructRef = gv.borrow_global().value_as(StructRef)
        r2: StructRef = r1.borrow_field(0).value_as(StructRef)
        r3: Reference = r2.borrow_field(0).value_as(Reference)
        assert(r3.read_ref().equals(Value.Uint64(0)))
    lambda3()

