from __future__ import annotations
from enum import IntEnum
from mol.functional_tests.errors import ErrorKind, ErrorKindTag

# Indicates one step in the pipeline the given move module/program goes through.
#  Ord is derived as we need to be able to determine if one stage is before another.
class Stage(IntEnum):
    Compiler = 1
    Verifier = 2
    Serializer = 3
    Runtime = 4

    @classmethod
    def from_str(cls, s: str) -> Stage:
        if s == "compiler":
            return Stage.Compiler
        if s == "verifier":
            return Stage.Verifier
        if s == "serializer":
            return Stage.Serializer
        if s == "runtime":
            return Stage.Runtime

        raise ErrorKind(ErrorKindTag.Other, f"unrecognized stage '{s}'")

