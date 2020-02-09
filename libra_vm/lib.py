from __future__ import annotations
from enum import IntEnum

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

    @staticmethod
    def variants() ->  List[IndexKind]:
        # XXX ensure this list stays up to date!
        return [
            ByteArrayPool,
            ModuleHandle,
            StructHandle,
            FunctionHandle,
            StructDefinition,
            FieldDefinition,
            FunctionDefinition,
            TypeSignature,
            FunctionSignature,
            LocalsSignature,
            Identifier,
            AddressPool,
            LocalPool,
            CodeDefinition,
            TypeParameter,
        ]


    def __str__(self):
        desc = {
            ModuleHandle : "module handle",
            StructHandle : "class handle",
            FunctionHandle : "function handle",
            StructDefinition : "class definition",
            FieldDefinition : "field definition",
            FunctionDefinition : "function definition",
            TypeSignature : "type signature",
            FunctionSignature : "function signature",
            LocalsSignature : "locals signature",
            Identifier : "identifier",
            ByteArrayPool : "byte_array pool",
            AddressPool : "address pool",
            LocalPool : "local pool",
            CodeDefinition : "code definition pool",
            TypeParameter : "type parameter",
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

