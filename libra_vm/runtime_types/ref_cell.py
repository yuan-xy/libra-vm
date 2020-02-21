from enum import IntEnum

class BorrowFlag(IntEnum):
    UNUSED = 0
    #READ >= 1
    WRITE = -1

class Ref:
    def __init__(self, obj, cell):
        self.v0 = obj
        self._cell = cell

    def __del__(self):
        self._cell.unborrow()

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

    def borrow(self) -> Ref:
        assert self.flag >= BorrowFlag.UNUSED
        self.flag += 1
        return Ref(self.v0, self)

    def unborrow(self):
        assert self.flag > BorrowFlag.UNUSED
        self.flag -= 1

    def borrow_mut(self) -> RefMut:
        assert self.flag == BorrowFlag.UNUSED
        self.flag = BorrowFlag.WRITE
        return RefMut(self.v0, self)

    def borrow_mut_set(self, value):
        refmut = self.borrow_mut()
        refmut.cell.v0 = value

    def unborrow_mut(self):
        assert self.flag == BorrowFlag.WRITE
        self.flag = BorrowFlag.UNUSED


from canoser.types import type_mapping
from canoser.base import Base


class RefCellCanoser(RefCell, Base):
    delegate_type = 'delegate'

    @classmethod
    def dtype(cls):
        return type_mapping(cls.delegate_type)

    @classmethod
    def encode(cls, value):
        return cls.dtype().encode(value.v0)

    @classmethod
    def decode(cls, cursor):
        v0 = cls.dtype().decode(cursor)
        return cls(v0)

    @classmethod
    def check_value(cls, value):
        cls.dtype().check_value(value.v0)

    def to_json_serializable(self):
        return self.__class__.dtype().to_json_serializable(self.v0)

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return self.v0 == other.v0 and self.borrow == other.borrow
