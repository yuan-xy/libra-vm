from vm.file_format_common import SerializedType
from vm.file_format import SignatureToken, StructHandleIndex
from typing import List, Tuple, Optional
from canoser import Uint16

BOOL = SignatureToken(SerializedType.BOOL)
U8 = SignatureToken(SerializedType.U8)
U64 = SignatureToken(SerializedType.U64)
U128 = SignatureToken(SerializedType.U128)
ADDRESS = SignatureToken(SerializedType.ADDRESS)

def Struct(struct : Tuple[StructHandleIndex, List[SignatureToken]], opt=None) -> SignatureToken:
    if opt is not None:
        struct = (struct, opt)
    return SignatureToken(SerializedType.STRUCT, struct)

def Reference(ref : SignatureToken) -> SignatureToken:
    return SignatureToken(SerializedType.REFERENCE, reference=ref)


def MutableReference(ref : SignatureToken) -> SignatureToken:
    return SignatureToken(SerializedType.MUTABLE_REFERENCE, reference=ref)


def TypeParameter(idx : Uint16) -> SignatureToken:
    return SignatureToken(SerializedType.TYPE_PARAMETER, typeParameter=idx)

def Vector(vector_type: SignatureToken) -> SignatureToken:
    return SignatureToken(SerializedType.VECTOR, vector_type=vector_type)

VectorU8 = Vector(U8)

