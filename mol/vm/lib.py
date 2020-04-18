from __future__ import annotations
from enum import IntEnum
from typing import List

# Represents a kind of index -- useful for error messages.
class IndexKind(IntEnum):
    ModuleHandle=0,
    StructHandle=1,
    FunctionHandle=2,
    StructDefinition=3,
    FieldDefinition=4,
    FunctionDefinition=5,
    TypeSignature=6,
    FunctionSignature=7,
    LocalsSignature=8,
    Identifier=9,
    ByteArrayPool=10,
    AddressPool=11,
    LocalPool=12,
    CodeDefinition=13,
    TypeParameter=14,

    @classmethod
    def variants(cls) ->  List[IndexKind]:
        # XXX ensure this list stays up to date!
        return [
            IndexKind.ByteArrayPool,
            IndexKind.ModuleHandle,
            IndexKind.StructHandle,
            IndexKind.FunctionHandle,
            IndexKind.StructDefinition,
            IndexKind.FieldDefinition,
            IndexKind.FunctionDefinition,
            IndexKind.TypeSignature,
            IndexKind.FunctionSignature,
            IndexKind.LocalsSignature,
            IndexKind.Identifier,
            IndexKind.AddressPool,
            IndexKind.LocalPool,
            IndexKind.CodeDefinition,
            IndexKind.TypeParameter,
        ]


    def __str__(self):
        desc = {
            IndexKind.ModuleHandle : "module handle",
            IndexKind.StructHandle : "class handle",
            IndexKind.FunctionHandle : "function handle",
            IndexKind.StructDefinition : "class definition",
            IndexKind.FieldDefinition : "field definition",
            IndexKind.FunctionDefinition : "function definition",
            IndexKind.TypeSignature : "type signature",
            IndexKind.FunctionSignature : "function signature",
            IndexKind.LocalsSignature : "locals signature",
            IndexKind.Identifier : "identifier",
            IndexKind.ByteArrayPool : "byte_array pool",
            IndexKind.AddressPool : "address pool",
            IndexKind.LocalPool : "local pool",
            IndexKind.CodeDefinition : "code definition pool",
            IndexKind.TypeParameter : "type parameter",
        }
        return desc[self]


# TODO: is this outdated
# Represents the kind of a signature token.
class SignatureTokenKind(IntEnum):
    # Any sort of owned value that isn't an array (Integer, Bool, Struct etc).
    Value=0,
    # A reference.
    Reference=1,
    # A mutable reference.
    MutableReference=2,

