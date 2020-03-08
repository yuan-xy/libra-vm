from __future__ import annotations
from canoser import Uint32
from dataclasses import dataclass

ByteIndex = Uint32

@dataclass
class Span:
    start: ByteIndex = 0
    end: ByteIndex = 0

    @classmethod
    def new(cls, start, end):
        assert end >= start
        return cls(start, end)

    def __lt__(self, other):
        return (self,start, self.end).__lt__((other.start, other.end))

