from __future__ import annotations
from canoser import Struct, Uint32

ByteIndex = Uint32


class Span(Struct):
    _fields = [
        ('start', ByteIndex),
        ('end', ByteIndex),
    ]

    @classmethod
    def new(cls, start, end):
        assert end >= start
        return cls(start, end)

    def __lt__(self, other):
        return (self.start, self.end).__lt__((other.start, other.end))

