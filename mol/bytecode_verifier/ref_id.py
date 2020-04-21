from libra.rustlib import usize
from dataclasses import dataclass
from mol.move_core import JsonPrintable

# This module implements the RefID type used for borrow checking in the abstract interpreter.
# A RefID instance represents an arbitrary reference or access path.
# The integer inside a RefID is meaningless; only equality and borrow relationships are
# meaningful.

@dataclass
class RefID(JsonPrintable):
    v0: usize

    def to_json(self, indent=None):
        return self.to_json_serializable()

    def to_json_serializable(self):
        return f"RefID({self.v0})"

    def __hash__(self):
        return self.v0.__hash__()

    def isa(self, n: usize) -> bool:
        return self.v0 == n


    def inner(self) -> usize:
        return self.v0

