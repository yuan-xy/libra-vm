from libra.rustlib import usize
from dataclasses import dataclass

# This module implements the RefID type used for borrow checking in the abstract interpreter.
# A RefID instance represents an arbitrary reference or access path.
# The integer inside a RefID is meaningless; only equality and borrow relationships are
# meaningful.

@dataclass
class RefID:
    v0: usize


    def isa(self, n: usize) -> bool:
        return self.v0 == n


    def inner(self) -> usize:
        return self.v0

