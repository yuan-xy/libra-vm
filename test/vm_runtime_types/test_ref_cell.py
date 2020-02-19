from libra_vm.runtime_types.ref_cell import *
import pytest


def test_refcell():
    x = "asdf"
    refcell = RefCell(x)
    y = refcell.into_inner()
    assert y == x
    b1 = refcell.borrow()
    b2 = refcell.borrow()
    assert refcell.flag == 2
    assert b1.v0 == b2.v0
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
        with pytest.raises(AssertionError):
            refcell.borrow_mut()
        with pytest.raises(AssertionError):
            refcell.borrow()
    assert refcell.flag == 0




