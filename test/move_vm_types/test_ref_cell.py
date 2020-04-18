from mol.move_vm.types.ref_cell import *
from canoser import DelegateT
import pytest

class StrRefCell(RefCellCanoser):
    delegate_type = str

def test_canoser():
    x = StrRefCell("asdf")
    ser = x.serialize()
    x2 = StrRefCell.deserialize(ser)
    assert x.v0 == x2.v0

def test_refcell():
    x = ['a', 'b', 'c']
    refcell = RefCell(x)
    y = refcell.into_inner()
    assert y == x
    b1 = refcell.borrow()
    b2 = refcell.borrow()
    assert refcell.flag == 2
    assert b1.v0 == b2.v0
    #WARNING: borrow mutable obj, you can modify the obj, BUT you should avoid do this.
    b1.v0.append("d")
    assert b2.v0 == ['a', 'b', 'c', 'd']
    assert refcell.v0 == ['a', 'b', 'c', 'd']
    with pytest.raises(AssertionError):
        refcell.borrow_mut()
    del b1
    assert refcell.flag == 1
    del b2
    assert refcell.flag == 0
    def lambda0():
        mb1 = refcell.borrow_mut()
        assert refcell.flag == -1
        assert mb1.v0 == x
        mb1.v0 = "change by value"
        assert refcell.v0 == ['a', 'b', 'c', 'd']
        mb1.cell.v0 = "change by ref"
        assert refcell.v0 == "change by ref"
        mb1.cell.v0 = x
        with pytest.raises(AssertionError):
            refcell.borrow_mut()
        with pytest.raises(AssertionError):
            refcell.borrow()
    lambda0()
    lambda0()
    assert refcell.flag == 0
    refcell2 = refcell
    assert refcell2.flag == 0
    ref2 = refcell2.borrow()
    assert refcell2.flag == 1
    assert refcell.flag == 1
    assert id(refcell) == id(refcell2)
    assert id(refcell.v0) == id(refcell2.v0)
    with pytest.raises(AssertionError):
        refcell.borrow_mut()
    assert refcell2.flag == 1
    del ref2
    assert refcell2.flag == 0
    refcell2.borrow() #borrow, and then throw the return value, so borrow returned.
    assert refcell2.flag == 0





