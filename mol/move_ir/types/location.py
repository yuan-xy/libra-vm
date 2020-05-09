from __future__ import annotations
from mol.move_ir.types.codespan import Span
from typing import List, Optional, Any, Union
from canoser import Struct
from dataclasses import dataclass

class Loc(Struct):
    _fields = [
        ('file', str),
        ('span', Span),
    ]

    def __lt__(self, other):
        if self.file == other.file:
            return self.span.__lt__(other.span)
        else:
            return self.file.__lt__(other.file)

    def to_json_serializable(self):
        amap = super().to_json_serializable()
        if hasattr(self, 'line_no'):
            amap["line_no"] = self.line_no
        return amap


@dataclass
class Spanned:
    loc: Loc
    value: Any


    NO_LOC_FILE = ""

    def unsafe_no_loc(cls, value: Any) -> Spanned:
        return cls(Loc(Spanned.NO_LOC_FILE, Span()), value)

    def __lt__(self, other):
        return self.value.__lt__(other.value)

    def __hash__(self):
        return self.value.__hash__()



# Function used to have nearly tuple-like syntax for creating a Spanned
def sp(loc: Loc, value: Any) -> Spanned:
    return Spanned(loc, value)

