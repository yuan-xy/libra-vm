from enum import IntEnum

class BorrowFlag(IntEnum):
    UNUSED = 0
    #READ >= 1
    WRITE = -1

class Ref:
    def __init__(self, obj, cell):
        self.v0 = obj
        self.cell = cell

    def __del__(self):
        self.cell.unborrow()

class RefMut:
    def __init__(self, obj, cell):
        self.v0 = obj
        self.cell = cell

    def __del__(self):
        self.cell.unborrow_mut()

class RefCell:
    def __init__(self, obj):
        self.v0 = obj
        self.flag = BorrowFlag.UNUSED
        #self.borrows = []

    def into_inner(self):
        assert self.flag == BorrowFlag.UNUSED
        return self.v0

    def borrow(self):
        assert self.flag >= BorrowFlag.UNUSED
        self.flag += 1
        return Ref(self.v0, self)

    def unborrow(self):
        assert self.flag > BorrowFlag.UNUSED
        self.flag -= 1

    def borrow_mut(self):
        assert self.flag == BorrowFlag.UNUSED
        self.flag = BorrowFlag.WRITE
        return RefMut(self.v0, self)

    def unborrow_mut(self):
        assert self.flag == BorrowFlag.WRITE
        self.flag = BorrowFlag.UNUSED

