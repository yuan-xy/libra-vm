from __future__ import annotations
from libra_vm.lib import IndexKind, SignatureTokenKind
from libra_vm.internals import ModuleIndex
from libra_vm.vm_exception import VMException
# use crate.{
#     access.ModuleAccess, check_bounds.BoundsChecker
# }
from libra.account_address import Address
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus
from libra.rustlib import ensure, bail, usize
from canoser import Uint8, Uint32, Uint16, Uint64, Uint128
from enum import IntEnum, unique
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# Binary format for transactions and modules.
#
# This module provides a simple Rust abstraction over the binary format. That is the format of
# modules stored on chain or the format of the code section of a transaction.
#
# `file_format_common.rs` provides the constant values for entities in the binary format.
# (*The binary format is evolving so please come back here in time to check evolutions.*)
#
# Overall the binary format is structured in a number of sections:
# - **Header**: this must start at offset 0 in the binary. It contains a blob that starts every
# Libra binary, followed by the version of the VM used to compile the code, and last is the
# number of tables present in this binary.
# - **Table Specification**: it's a number of tuple of the form
# `(table type, starting_offset, byte_count)`. The number of entries is specified in the
# header (last entry in header). There can only be a single entry per table type. The
# `starting offset` is from the beginning of the binary. Tables must cover the entire size of
# the binary blob and cannot overlap.
# - **Table Content**: the serialized form of the specific entries in the table. Those roughly
# map to the structs defined in this module. Entries in each table must be unique.
#
# We have two formats: one for modules here represented by `CompiledModule`, another
# for transaction scripts which is `CompiledScript`. Building those tables and passing them
# to the serializer (`serializer.rs`) generates a binary of the form described. Vectors in
# those structs translate to tables and table specifications.


# Generic index into one of the tables in the binary format.
TableIndex = Uint16

@dataclass
class Index(TableIndex, ModuleIndex):
    v0: TableIndex = 0

    def into_index(self) -> usize:
        return self.v0


def define_index(name: str, kind: IndexKind, doc: str) -> None:
    clazz = type(name, (Index,), {})
    clazz.KIND = kind
    clazz.__doc__ = doc
    return clazz


class ModuleHandleIndex(Index):
    KIND = IndexKind.ModuleHandle


class StructHandleIndex(Index):
    KIND = IndexKind.StructHandle


class FunctionHandleIndex(Index):
    KIND = IndexKind.FunctionHandle


class IdentifierIndex(Index):
    KIND = IndexKind.Identifier


class ByteArrayPoolIndex(Index):
    KIND = IndexKind.ByteArrayPool


class AddressPoolIndex(Index):
    KIND = IndexKind.AddressPool


class TypeSignatureIndex(Index):
    KIND = IndexKind.TypeSignature


class FunctionSignatureIndex(Index):
    KIND = IndexKind.FunctionSignature


class LocalsSignatureIndex(Index):
    KIND = IndexKind.LocalsSignature


class StructDefinitionIndex(Index):
    KIND = IndexKind.StructDefinition


class FieldDefinitionIndex(Index):
    KIND = IndexKind.FieldDefinition


class FunctionDefinitionIndex(Index):
    KIND = IndexKind.FunctionDefinition


# Index of a local variable in a function.
#
# Bytecodes that operate on locals carry indexes to the locals of a function.
LocalIndex = Uint8
# Max number of fields in a `StructDefinition`.
MemberCount = Uint16
# Index into the code stream for a jump. The offset is relative to the beginning of
# the instruction stream.
CodeOffset = Uint16

# The pool of identifiers.
IdentifierPool = List[Identifier]
# The pool of `ByteArray` literals.
ByteArrayPool = List[bytearray]
# The pool of `Address` literals.
#
# Code references have a literal addresses in `ModuleHandle`s. Literal references to data in
# the blockchain are also published here.
AddressPool = List[Address]

#TypeSignaturePool Moved behind TypeSignature to avoid NameError: name 'TypeSignature' is not defined
#TypeSignaturePool = List[TypeSignature]
#FunctionSignaturePool = List[FunctionSignature]
#LocalsSignaturePool = List[LocalsSignature]

# TODO: "<SELF>" only passes the validator for identifiers because it is special cased. Whenever
# "<SELF>" is removed, so should the special case in identifier.rs.
SELF_MODULE_NAME: Identifier = "<SELF>"

def self_module_name() -> IdentStr:
    return SELF_MODULE_NAME


# Index 0 into the LocalsSignaturePool, which is guaranteed to be an empty list.
# Used to represent function/class instantiation with no type actuals -- effectively
# non-generic functions and structs.
NO_TYPE_ACTUALS: LocalsSignatureIndex = LocalsSignatureIndex(0)

# HANDLES:
# Handles are structs that accompany opcodes that need references: a type reference,
# or a function reference (a field reference being available only within the module that
# defrines the field can be a definition).
# Handles refer to both internal and external "entities" and are embedded as indexes
# in the instruction stream.
# Handles define resolution. Resolution is assumed to be by (name, signature)

# A `ModuleHandle` is a reference to a MOVE module. It is composed by an `address` and a `name`.
#
# A `ModuleHandle` uniquely identifies a code resource in the blockchain.
# The `address` is a reference to the account that holds the code and the `name` is used as a
# key in order to load the module.
#
# Modules live in the *code* namespace of an LibraAccount.
#
# Modules introduce a scope made of all types defined in the module and all functions.
# Type definitions (fields) are private to the module. Outside the module a
# Type is an opaque handle.
@dataclass
class ModuleHandle:
    # Index into the `AddressPool`. Identifies the account that holds the module.
    address: AddressPoolIndex
    # The name of the module published in the code section for the account in `address`.
    name: IdentifierIndex


# A `StructHandle` is a reference to a user defined type. It is composed by a `ModuleHandle`
# and the name of the type within that module.
#
# A type in a module is uniquely identified by its name and as such the name is enough
# to perform resolution.
#
# The `StructHandle` is polymorphic: it can have type parameters in its fields and carries the
# kind constraints for these type parameters (empty list for non-generic structs). It also
# carries the kind (resource/copyable) of the class itself so that the verifier can check
# resource semantic without having to load the referenced type.
#
# At link time kind checking is performed and an error is reported if there is a
# mismatch with the definition.

@dataclass
class StructHandle:
    # The module that defines the type.
    module: ModuleHandleIndex
    # The name of the type.
    name: IdentifierIndex
    # There are two ways for a type to have the Kind resource
    # 1) If it has a type argument of resource
    # 2) If it was declared as a resource
    # These "declared" resources are referred to as *nominal resources*
    #
    # If `is_nominal_resource` is True, it is a *nominal resource*
    is_nominal_resource: bool
    # The type formals (identified by their index into the vec) and their kind constraints
    type_formals: List[Kind]


# A `FunctionHandle` is a reference to a function. It is composed by a
# `ModuleHandle` and the name and signature of that function within the module.
#
# A function within a module is uniquely identified by its name. No overloading is allowed
# and the verifier enforces that property. The signature of the function is used at link time to
# ensure the function reference is valid and it is also used by the verifier to type check
# function calls.
@dataclass
class FunctionHandle:
    # The module that defines the function.
    module: ModuleHandleIndex
    # The name of the function.
    name: IdentifierIndex
    # The signature of the function.
    signature: FunctionSignatureIndex


# DEFINITIONS:
# Definitions are the module code. So the set of types and functions in the module.

# `StructFieldInformation` indicates whether a class is native or has user-specified fields
class StructFieldInformationTag(IntEnum):
    Native = 0
    Declared = 1


@dataclass
class StructFieldInformation:
    tag: StructFieldInformationTag
    # The number of fields in this type.
    field_count: Optional[MemberCount]
    # The starting index for the fields of this type. `FieldDefinition`s for each type must
    # be consecutively stored in the `FieldDefinition` table.
    fields: Optional[FieldDefinitionIndex]



# A `StructDefinition` is a type definition. It either indicates it is native or
# defines all the user-specified fields declared on the type.
@dataclass
class StructDefinition:
    # The `StructHandle` for this `StructDefinition`. This has the name and the resource flag
    # for the type.
    class_handle: StructHandleIndex
    # Contains either
    # - Information indicating the class is native and has no accessible fields
    # - Information indicating the number of fields and the start `FieldDefinitionIndex`
    field_information: StructFieldInformation


    def declared_field_count(self) -> MemberCount:
        if self.field_information.tag == StructFieldInformationTag.Native:
            # TODO we might want a more informative error here
            raise VMException([VMStatus(StatusCode.LINKER_ERROR)])
        elif self.field_information.tag == StructFieldInformationTag.Native:
            return field_count
        else:
            bail("unreachable!")


# A `FieldDefinition` is the definition of a field: the type the field is defined on,
# its name and the field type.
@dataclass
class FieldDefinition:
    # The type (resource or unrestricted) the field is defined on.
    class_: StructHandleIndex
    # The name of the field.
    name: IdentifierIndex
    # The type of the field.
    signature: TypeSignatureIndex


# A `FunctionDefinition` is the implementation of a function. It defines
# the *prototype* of the function and the function body.
@dataclass
class FunctionDefinition:
    # The prototype of the function (module, name, signature).
    function: FunctionHandleIndex = field(default_factory=FunctionHandleIndex)
    # Flags for this function (private, public, native, etc.)
    flags: Uint8 = 0
    # List of nominal resources (declared in this module) that the procedure might access
    # Either through: BorrowGlobal, MoveFrom, or transitively through another procedure
    # This list of acquires grants the borrow checker the ability to statically verify the safety
    # of references into global storage
    #
    # Not in the signature as it is not needed outside of the declaring module
    #
    # Note, there is no LocalsSignatureIndex with each class definition index, as global
    # resources cannot currently take type arguments
    acquires_global_resources: List[StructDefinitionIndex] = field(default_factory=list)
    # Code for this function.
    code: CodeUnit = field(default_factory='CodeUnit')


    # Returns whether the FunctionDefinition is public.
    def is_public(self) -> bool:
        return self.flags & CodeUnit.PUBLIC != 0

    # Returns whether the FunctionDefinition is native.
    def is_native(self) -> bool:
        return self.flags & CodeUnit.NATIVE != 0


# Signature
# A signature can be for a type (field, local) or for a function - return type: (arguments).
# They both go into the signature table so there is a marker that tags the signature.
# Signature usually don't carry a size and you have to read them to get to the end.

# A type definition. `SignatureToken` allows the definition of the set of known types and their
# composition.
@dataclass
class TypeSignature:
    v0: SignatureToken

# A `FunctionSignature` describes the types of a function.
#
# The `FunctionSignature` is polymorphic: it can have type parameters in the argument and return
# types and carries kind constraints for those type parameters (empty list for non-generic
# functions).
@dataclass
class FunctionSignature:
    # The list of return types.
    return_types: List[SignatureToken]
    # The list of arguments to the function.
    arg_types: List[SignatureToken]
    # The type formals (identified by their index into the vec) and their kind constraints
    type_formals: List[Kind]


# A `LocalsSignature` is the list of locals used by a function.
#
# Locals include the arguments to the function from position `0` to argument `count - 1`.
# The remaining elements are the type of each local.
@dataclass
class LocalsSignature:
    v0: List[SignatureToken]

    def __len__(self) -> usize:
        return self.v0.__len__()


    # Whether the function has no locals (both arguments or locals).
    #[inline]
    def is_empty(self) -> bool:
        return bool(self.v0)


# The pool of `TypeSignature` instances. Those are system and user types used and
# their composition (e.g. &U64).
TypeSignaturePool = List[TypeSignature]
# The pool of `FunctionSignature` instances.
FunctionSignaturePool = List[FunctionSignature]
# The pool of `LocalsSignature` instances. Every function definition must define the set of
# locals used and their types.
LocalsSignaturePool = List[LocalsSignature]


# Type parameters are encoded as indices. This index can also be used to lookup the kind of a
# type parameter in the `FunctionSignature/Handle` and `StructHandle`.
TypeParameterIndex = Uint16

# A `Kind` classifies types into sets with rules each set must follow.
#
# Currently there are three kinds in Move: `All`, `Resource` and `Unrestricted`.
class Kind(IntEnum):
    # Represents the super set of all types. The type might actually be a `Resource` or
    # `Unrestricted` A type might be in this set if it is not known to be a `Resource` or
    # `Unrestricted`
    #   - This occurs when there is a type parameter with this kind as a constraint
    All = 0
    # `Resource` types must follow move semantics and various resource safety rules, namely:
    # - `Resource` values cannot be copied
    # - `Resource` values cannot be popped, i.e. they must be used
    Resource = 1
    # `Unrestricted` types do not need to follow the `Resource` rules.
    # - `Unrestricted` values can be copied
    # - `Unrestricted` values can be popped
    Unrestricted =2


    # Checks if the given kind is a sub-kind of another.
    def is_sub_kind_of(self, k: Kind) -> bool:
        if k == All:
            return True
        if self == Resource and k == Resource:
            return True
        if self == Unrestricted and k == Unrestricted:
            return True
        return False

    # Helper function to determine the kind of a class instance by taking the kind of a type
    # actual and join it with the existing partial result.
    def join(self, other: Kind) -> Kind:
        if self == Kind.All or other == Kind.All:
            return Kind.All
        if self == Kind.Resource or other == Kind.Resource:
            return Kind.Resource
        if self == Kind.Unrestricted and other == Kind.Unrestricted:
            return Kind.Unrestricted
        bail("unreachable!")


# A `SignatureToken` is a type declaration for a location.
#
# Any location in the system has a TypeSignature.
# A TypeSignature is also used in composed signatures.
#
# A SignatureToken can express more types than the VM can handle safely, and correctness is
# enforced by the verifier.
class SignatureTokenTag(IntEnum):
    # Boolean, `true` or `false`.
    Bool=0,
    # Unsigned integers, 8 bits length.
    U8=1,
    # Unsigned integers, 64 bits length.
    U64=2,
    # Unsigned integers, 128 bits length.
    U128=3,
    # ByteArray, variable size, immutable byte array.
    ByteArray=4,
    # Address, a 32 bytes immutable type.
    Address=5,
    # MOVE user type, resource or unrestricted
    Struct=6
    # Reference to a type.
    Reference=7
    # Mutable reference to a type.
    MutableReference=8
    # Type parameter.
    TypeParameter=9

    def is_primitive(self) -> bool:
        if self in [Bool ,  U8 ,  U64 ,  U128 ,  ByteArray ,  Address]:
            return True
        else:
            return False

    def is_integer(self) -> bool:
        if self in [U8 ,  U64 ,  U128]:
            return True
        else:
            return False


@dataclass
class SignatureToken:
    tag: SignatureTokenTag
    # MOVE user type, resource or unrestricted
    struct : Tuple[StructHandleIndex, List[SignatureToken]]
    # (Mutable) Reference to a type.
    reference : SignatureToken
    # Type parameter.
    typeParameter : TypeParameterIndex


    # If a `SignatureToken` is a reference it returns the underlying type of the reference (e.g.
    # U64 for &U64).
    @classmethod
    def get_struct_handle_from_reference(cls,
        reference_signature: SignatureToken,
    ) -> Optional[StructHandleIndex]:
        if reference_signature.tag == SignatureTokenTag.Reference or\
            reference_signature.tag == SignatureTokenTag.MutableReference:
            signature = reference_signature.reference
            if signature.tag == SignatureTokenTag.Struct:
                (idx, _) = signature.struct
                return idx
            else:
                return None
        return None


    # Returns the type actuals if the signature token is a reference to a class instance.
    def get_type_actuals_from_reference(self) -> Optional[List[SignatureToken]]:
        if self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            box_ = self.reference
            if box_.tag == SignatureTokenTag.Struct:
                (_, tys) = box_.struct
                return tys
        return None


    # Returns the "value kind" for the `SignatureToken`
    def signature_token_kind(self) -> SignatureTokenKind:
        # TODO: SignatureTokenKind is out-dated. fix/update/remove SignatureTokenKind and see if
        # this function needs to be cleaned up
        if self.tag == SignatureTokenTag.Reference:
            return SignatureTokenKind.Reference
        elif self.tag == SignatureTokenTag.MutableReference:
            return SignatureTokenKind.MutableReference
        else:
            return SignatureTokenKind.Value


    # Returns the `StructHandleIndex` for a `SignatureToken` that contains a reference to a user
    # defined type (a resource or unrestricted type).
    def struct_index(self) -> Optional[StructHandleIndex]:
        if self.tag == SignatureTokenTag.Struct:
            (sh_idx, _) = self.struct
            return sh_idx
        elif self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            token = self.reference
            return token.struct_index()
        else:
            return None


    # Returns `true` if the `SignatureToken` is a primitive type.
    def is_primitive(self) -> bool:
        return self.tag.is_primitive()

    # Returns `true` if the `SignatureToken` is an integer type.
    def is_integer(self) -> bool:
        return self.tag.is_integer()


    # Checks if the signature token is usable for Eq and Neq.
    #
    # Currently equality operations are only allowed on:
    # - Bool
    # - U64
    # - ByteArray
    # - Address
    # - Reference or Mutable reference to these types
    def allows_equality(self) -> bool:
        if self.tag == SignatureTokenTag.Struct:
            return False
        elif self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            token = self.reference
            return token.is_primitive()
        else:
            return self.is_primitive()


    # Returns True if the `SignatureToken` is any kind of reference (mutable and immutable).
    def is_reference(self) -> bool:
        if self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            return True
        else:
            return False


    # Returns True if the `SignatureToken` is a mutable reference.
    def is_mutable_reference(self) -> bool:
        return self.tag == SignatureTokenTag.MutableReferenc


    # Set the index to this one. Useful for random testing.
    #
    # Panics if this token doesn't contain a class handle.
    def debug_set_sh_idx(self, sh_idx: StructHandleIndex):
        if self.tag == SignatureTokenTag.Struct:
            _wrapped, _x = self.struct
            self.struct = (sh_idx, _x)
        elif self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            token = self.reference
            token.debug_set_sh_idx(sh_idx)
        else:
            bail(
                "debug_set_sh_idx (to {}) called for non-class token {}",
                sh_idx, other
            )


    # Creating a new type by Substituting the type variables with type actuals.
    def substitute(self, tys: List[SignatureToken]) -> SignatureToken:
        if self.is_primitive():
            return deepcopy(self)
        elif self.tag == SignatureTokenTag.Struct:
            (idx, actuals) = self.struct
            ret = SignatureToken(self.tag)
            ret.struct = (idx, [ty.substitute(tys) for ty in actuals])
            return ret
        elif self.tag == SignatureTokenTag.Reference or self.tag == SignatureTokenTag.MutableReference:
            ty = self.reference
            ret = SignatureToken(self.tag)
            ret.reference = ty.substitute(tys)
            return ret
        elif self.tag == SignatureTokenTag.TypeParameter:
            idx = self.typeParameter
            return deepcopy(tys[int(idx)])
        else:
            bail("unreachable!")

    # Returns the kind of the signature token in the given context (module, function/struct).
    # The context is needed to determine the kinds of structs & type variables.
    @classmethod
    def kind(cls,
        atuple: Tuple[List[StructHandle], List[Kind]],
        ty: SignatureToken,
    ) -> Kind:
        (struct_handles, type_formals) = atuple
        if ty.is_primitive() or ty.is_reference():
            return Kind.Unrestricted
        elif ty.tag == SignatureTokenTag.TypeParameter:
            idx = ty.typeParameter
            return type_formals[idx]
        elif ty.tag == SignatureTokenTag.Struct:
            (idx, tys) = ty.struct
            # Get the class handle at idx. Note the index could be out of bounds.
            sh = struct_handles[idx.v0]
            if sh.is_nominal_resource:
                return Kind.Resource
            # Gather the kinds of the type actuals.
            kinds = [cls.kind((struct_handles, type_formals), ty) for ty in tys]

            # Derive the kind of the struct.
            #   - If any of the type actuals is `all`, then the class is `all`.
            #     - `all` means some part of the type can be either `resource` or
            #       `unrestricted`.
            #     - Therefore it is also impossible to determine the kind of the type as a
            #       whole, and thus `all`.
            #   - If none of the type actuals is `all`, then the class is a resource if
            #     and only if one of the type actuals is `resource`.
            ret = Kind.Unrestricted
            for x in kinds:
                ret = Kind.join(ret, x)
            return ret
        else:
            bail("unreachable!")


# A `CodeUnit` is the body of a function. It has the function header and the instruction stream.
@dataclass
class CodeUnit:
    # Max stack size for the function - currently unused.
    max_stack_size: Uint16 = 0
    # List of locals type. All locals are typed.
    locals: LocalsSignatureIndex = field(default_factory=LocalsSignatureIndex)
    # Code stream, function body.
    code: List[Bytecode] = field(default_factory=list)

    # Function can be invoked outside of its declaring module.
    PUBLIC = 0x1
    # A native function implemented in Rust.
    NATIVE = 0x2


# `Bytecode` is a VM instruction of variable size. The type of the bytecode (opcode) defines
# the size of the bytecode.
#
# Bytecodes operate on a stack machine and each bytecode has side effect on the stack and the
# instruction stream.
@unique
class BytecodeTag(IntEnum):
    # Pop and discard the value at the top of the stack.
    # The value on the stack must be an unrestricted type.
    #
    # Stack transition:
    #
    # ```..., value -> ...```
    Pop=1
    # Return from function, possibly with values according to the return types in the
    # function signature. The returned values are pushed on the stack.
    # The function signature of the function being executed defines the semantic of
    # the Ret opcode.
    #
    # Stack transition:
    #
    # ```..., arg_val(1), ..., arg_val(n) -> ..., return_val(1), ..., return_val(n)```
    Ret=2
    # Branch to the instruction at position `CodeOffset` if the value at the top of the stack
    # is True. Code offsets are relative to the start of the instruction stream.
    #
    # Stack transition:
    #
    # ```..., bool_value -> ...```
    BrTrue=3
    # Branch to the instruction at position `CodeOffset` if the value at the top of the stack
    # is False. Code offsets are relative to the start of the instruction stream.
    #
    # Stack transition:
    #
    # ```..., bool_value -> ...```
    BrFalse=4
    # Branch unconditionally to the instruction at position `CodeOffset`. Code offsets are
    # relative to the start of the instruction stream.
    #
    # Stack transition: none
    Branch=5
    # Push a U8 constant onto the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint8_value```
    LdU8=6
    # Push a U64 constant onto the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint64_value```
    LdU64=7
    # Push a U128 constant onto the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., u128_value```
    LdU128=8
    # Convert the value at the top of the stack into Uint8.
    #
    # Stack transition:
    #
    # ```..., integer_value -> ..., Uint8_value```
    CastU8=9
    # Convert the value at the top of the stack into Uint64.
    #
    # Stack transition:
    #
    # ```..., integer_value -> ..., Uint8_value```
    CastU64=10
    # Convert the value at the top of the stack into u128.
    #
    # Stack transition:
    #
    # ```..., integer_value -> ..., u128_value```
    CastU128=11
    # Push a `ByteArray` literal onto the stack. The `ByteArray` is loaded from the
    # `ByteArrayPool` via `ByteArrayPoolIndex`.
    #
    # Stack transition:
    #
    # ```... -> ..., bytearray_value```
    LdByteArray=12
    # Push an 'Address' literal onto the stack. The address is loaded from the
    # `AddressPool` via `AddressPoolIndex`.
    #
    # Stack transition:
    #
    # ```... -> ..., address_value```
    LdAddr=13
    # Push `true` onto the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., True```
    LdTrue=14
    # Push `false` onto the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., False```
    LdFalse=15
    # Push the local identified by `LocalIndex` onto the stack. The value is copied and the
    # local is still safe to use.
    #
    # Stack transition:
    #
    # ```... -> ..., value```
    CopyLoc=16
    # Push the local identified by `LocalIndex` onto the stack. The local is moved and it is
    # invalid to use from that point on, unless a store operation writes to the local before
    # any read to that local.
    #
    # Stack transition:
    #
    # ```... -> ..., value```
    MoveLoc=17
    # Pop value from the top of the stack and store it into the function locals at
    # position `LocalIndex`.
    #
    # Stack transition:
    #
    # ```..., value -> ...```
    StLoc=18
    # Call a function. The stack has the arguments pushed first to last.
    # The arguments are consumed and pushed to the locals of the function.
    # Return values are pushed on the stack and available to the caller.
    #
    # Stack transition:
    #
    # ```..., arg(1), arg(2), ...,  arg(n) -> ..., return_value(1), return_value(2), ...,
    # return_value(k)```
    Call=19
    # Create an instance of the type specified via `StructHandleIndex` and push it on the stack.
    # The values of the fields of the struct, in the order they appear in the class declaration,
    # must be pushed on the stack. All fields must be provided.
    #
    # A Pack instruction must fully initialize an instance.
    #
    # Stack transition:
    #
    # ```..., field(1)_value, field(2)_value, ..., field(n)_value -> ..., instance_value```
    Pack=20
    # Destroy an instance of a type and push the values bound to each field on the
    # stack.
    #
    # The values of the fields of the instance appear on the stack in the order defined
    # in the class definition.
    #
    # This order makes Unpack<T> the inverse of Pack<T>. So `Unpack<T>; Pack<T>` is the identity
    # for class T.
    #
    # Stack transition:
    #
    # ```..., instance_value -> ..., field(1)_value, field(2)_value, ..., field(n)_value```
    Unpack=21
    # Read a reference. The reference is on the stack, it is consumed and the value read is
    # pushed on the stack.
    #
    # Reading a reference performs a copy of the value referenced. As such
    # ReadRef cannot be used on a reference to a Resource.
    #
    # Stack transition:
    #
    # ```..., reference_value -> ..., value```
    ReadRef=22
    # Write to a reference. The reference and the value are on the stack and are consumed.
    #
    #
    # The reference must be to an unrestricted type because Resources cannot be overwritten.
    #
    # Stack transition:
    #
    # ```..., value, reference_value -> ...```
    WriteRef=23
    # Convert a mutable reference to an immutable reference.
    #
    # Stack transition:
    #
    # ```..., reference_value -> ..., reference_value```
    FreezeRef=24
    # Load a mutable reference to a local identified by LocalIndex.
    #
    # The local must not be a reference.
    #
    # Stack transition:
    #
    # ```... -> ..., reference```
    MutBorrowLoc=25
    # Load an immutable reference to a local identified by LocalIndex.
    #
    # The local must not be a reference.
    #
    # Stack transition:
    #
    # ```... -> ..., reference```
    ImmBorrowLoc=26
    # Load a mutable reference to a field identified by `FieldDefinitionIndex`.
    # The top of the stack must be a mutable reference to a type that contains the field
    # definition.
    #
    # Stack transition:
    #
    # ```..., reference -> ..., field_reference```
    MutBorrowField=27
    # Load an immutable reference to a field identified by `FieldDefinitionIndex`.
    # The top of the stack must be a reference to a type that contains the field definition.
    #
    # Stack transition:
    #
    # ```..., reference -> ..., field_reference```
    ImmBorrowField=28
    # Return a mutable reference to an instance of type `StructDefinitionIndex` published at the
    # address passed as argument. Abort execution if such an object does not exist or if a
    # reference has already been handed out.
    #
    # Stack transition:
    #
    # ```..., address_value -> ..., reference_value```
    MutBorrowGlobal=29
    # Return an immutable reference to an instance of type `StructDefinitionIndex` published at
    # the address passed as argument. Abort execution if such an object does not exist or if a
    # reference has already been handed out.
    #
    # Stack transition:
    #
    # ```..., address_value -> ..., reference_value```
    ImmBorrowGlobal=30
    # Add the 2 Uint64 at the top of the stack and pushes the result on the stack.
    # The operation aborts the transaction in case of overflow.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Add=31
    # Subtract the 2 Uint64 at the top of the stack and pushes the result on the stack.
    # The operation aborts the transaction in case of underflow.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Sub=32
    # Multiply the 2 Uint64 at the top of the stack and pushes the result on the stack.
    # The operation aborts the transaction in case of overflow.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Mul=33
    # Perform a modulo operation on the 2 Uint64 at the top of the stack and pushes the
    # result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Mod=34
    # Divide the 2 Uint64 at the top of the stack and pushes the result on the stack.
    # The operation aborts the transaction in case of "divide by 0".
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Div=35
    # Bitwise OR the 2 Uint64 at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    BitOr=36
    # Bitwise AND the 2 Uint64 at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    BitAnd=37
    # Bitwise XOR the 2 Uint64 at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Xor=38
    # Logical OR the 2 bool at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., bool_value(1), bool_value(2) -> ..., bool_value```
    Or=39
    # Logical AND the 2 bool at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., bool_value(1), bool_value(2) -> ..., bool_value```
    And=40
    # Logical NOT the bool at the top of the stack and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., bool_value -> ..., bool_value```
    Not=41
    # Compare for equality the 2 value at the top of the stack and pushes the
    # result on the stack.
    # The values on the stack cannot be resources or they will be consumed and so destroyed.
    #
    # Stack transition:
    #
    # ```..., value(1), value(2) -> ..., bool_value```
    Eq=42
    # Compare for inequality the 2 value at the top of the stack and pushes the
    # result on the stack.
    # The values on the stack cannot be resources or they will be consumed and so destroyed.
    #
    # Stack transition:
    #
    # ```..., value(1), value(2) -> ..., bool_value```
    Neq=43
    # Perform a "less than" operation of the 2 Uint64 at the top of the stack and pushes the
    # result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., bool_value```
    Lt=44
    # Perform a "greater than" operation of the 2 Uint64 at the top of the stack and pushes the
    # result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., bool_value```
    Gt=45
    # Perform a "less than or equal" operation of the 2 Uint64 at the top of the stack and pushes
    # the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., bool_value```
    Le=46
    # Perform a "greater than or equal" than operation of the 2 Uint64 at the top of the stack
    # and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., bool_value```
    Ge=47
    # Abort execution with errorcode
    #
    #
    # Stack transition:
    #
    # ```..., errorcode -> ...```
    Abort=48
    # Get gas unit price from the transaction and pushes it on the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint64_value```
    GetTxnGasUnitPrice=49
    # Get max gas units set in the transaction and pushes it on the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint64_value```
    GetTxnMaxGasUnits=50
    # Get remaining gas for the given transaction at the point of execution of this bytecode.
    # The result is pushed on the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint64_value```
    GetGasRemaining=51
    # Get the sender address from the transaction and pushes it on the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., address_value```
    GetTxnSenderAddress=52
    # Returns whether or not a given address has an object of type StructDefinitionIndex
    # published already
    #
    # Stack transition:
    #
    # ```..., address_value -> ..., bool_value```
    Exists=53
    # Move the instance of type StructDefinitionIndex, at the address at the top of the stack.
    # Abort execution if such an object does not exist.
    #
    # Stack transition:
    #
    # ```..., address_value -> ..., value```
    MoveFrom=54
    # Move the instance at the top of the stack to the address of the sender.
    # Abort execution if an object of type StructDefinitionIndex already exists in address.
    #
    # Stack transition:
    #
    # ```..., value -> ...```
    MoveToSender=55
    # Get the sequence number submitted with the transaction and pushes it on the stack.
    #
    # Stack transition:
    #
    # ```... -> ..., Uint64_value```
    GetTxnSequenceNumber=56
    # Get the public key of the sender from the transaction and pushes it on the stack.
    #
    # Stack transition:
    #
    # ```..., -> ..., bytearray_value```
    GetTxnPublicKey=57
    # Shift the (second top value) left (top value) bits and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Shl=58
    # Shift the (second top value) right (top value) bits and pushes the result on the stack.
    #
    # Stack transition:
    #
    # ```..., Uint64_value(1), Uint64_value(2) -> ..., Uint64_value```
    Shr=59

    @classmethod
    def NUM_INSTRUCTIONS(cls):
        return len(cls)


NUMBER_OF_NATIVE_FUNCTIONS: usize = 17

@dataclass
class Bytecode:
    tag: BytecodeTag
    value: Any = None

    # Return True if this bytecode instruction always branches
    def is_unconditional_branch(self) -> bool:
        return self.tag in [BytecodeTag.Ret, BytecodeTag.Abort, BytecodeTag.Branch]

    # Return True if the branching behavior of this bytecode instruction depends on a runtime
    # value
    def is_conditional_branch(self) -> bool:
        return self.tag in [BytecodeTag.BrFalse, BytecodeTag.BrTrue]

    # Returns True if this bytecode instruction is either a conditional or an unconditional branch
    def is_branch(self) -> bool:
        return self.is_conditional_branch() or self.is_unconditional_branch()


    # Returns the offset that this bytecode instruction branches to, if any.
    # Note that return and abort are branch instructions, but have no offset.
    def offset(self) -> Optional[CodeOffset]:
        if self.tag in [BytecodeTag.BrFalse, BytecodeTag.BrTrue, BytecodeTag.Branch]:
            return self.value
        else:
            return None

    # Return the successor offsets of this bytecode instruction.
    def get_successors(pc: CodeOffset, code: List[Bytecode]) -> List[CodeOffset]:
        ensure(
            # The program counter could be added to at most twice and must remain
            # within the bounds of the code.
            pc <= Uint16.max_value - 2 and pc < code.__len__(),
            "Program counter out of bounds"
        )
        bytecode = code[pc]
        v = []

        offset = bytecode.offset()
        if offset:
            v.append(offset)

        next_pc = pc + 1
        if next_pc >= code.__len__():
            return v

        if not bytecode.is_unconditional_branch() and not next_pc in v:
            # avoid duplicates
            v.append(pc + 1)

        # always give successors in ascending order
        if v.__len__() > 1 and v[0] > v[1]:
            tmp = v[0]
            v[0] = v[1]
            v[1] = tmp

        return v


# A `CompiledProgram` defines the structure of a transaction to execute.
# It has two parts: modules to be published and a transaction script.
@dataclass
class CompiledProgram:
    # The modules to be published
    modules: List[CompiledModule]
    # The transaction script to execute
    script: CompiledScript



# Note that this doesn't derive either `Arbitrary` or `Default` while `CompiledScriptMut` does.
# That's because a CompiledScript is guaranteed to be valid while a CompiledScriptMut isn't.
# Contains the main function to execute and its dependencies.
#
# A CompiledScript does not have definition tables because it can only have a `main(args)`.
# A CompiledScript defines the constant pools (string, address, signatures, etc.), the handle
# tables (external code references) and it has a `main` definition.
class CompiledScript:
    v0: CompiledScriptMut

    # Returns the index of `main` in case a script is converted to a module.
    MAIN_INDEX: FunctionDefinitionIndex = FunctionDefinitionIndex(0)

    #impl ScriptAccess for CompiledScript:
    def as_script(self) -> CompiledScript:
        return self


    # Returns a reference to the inner `CompiledScriptMut`.
    def as_inner(self) -> CompiledScriptMut:
        return self.v0


    # Converts this instance into the inner `CompiledScriptMut`. Converting back to a
    # `CompiledScript` would require it to be verified again.
    def into_inner(self) -> CompiledScriptMut:
        return self.v0


    # Converts a `CompiledScript` into a `CompiledModule` for code that wants a uniform view of
    # both.
    #
    # If a `CompiledScript` has been bounds checked, the corresponding `CompiledModule` can be
    # assumed to pass the bounds checker as well.
    def into_module(self) -> CompiledModule:
        return CompiledModule(self.v0.into_module())


# A mutable version of `CompiledScript`. Converting to a `CompiledScript` requires this to pass
# the bounds checker.
@dataclass
class CompiledScriptMut:
    # Handles to all modules referenced.
    module_handles: List[ModuleHandle]
    # Handles to external/imported types.
    class_handles: List[StructHandle]
    # Handles to external/imported functions.
    function_handles: List[FunctionHandle]

    # Type pool. All external types referenced by the transaction.
    type_signatures: TypeSignaturePool
    # Function signature pool. The signatures of the function referenced by the transaction.
    function_signatures: FunctionSignaturePool
    # Locals signature pool. The signature of the locals in `main`.
    locals_signatures: LocalsSignaturePool

    # All identifiers used in this transaction.
    identifiers: IdentifierPool
    # ByteArray pool. The byte array literals used in the transaction.
    byte_array_pool: ByteArrayPool
    # Address pool. The address literals used in the module. Those include literals for
    # code references (`ModuleHandle`).
    address_pool: AddressPool

    # The main (script) to execute.
    main: FunctionDefinition


    # Converts this instance into `CompiledScript` after verifying it for basic internal
    # consistency. This includes bounds checks but no others.
    def freeze(self) -> CompiledScript:
        fake_module = self.into_module()
        return fake_module.freeze().into_script()


    # Converts a `CompiledScriptMut` to a `CompiledModule` for code that wants a uniform view
    # of both.
    def into_module(self) -> CompiledModuleMut:
        return CompiledModuleMut(
            module_handles=self.module_handles,
            struct_handles=self.struct_handles,
            function_handles=self.function_handles,

            type_signatures=self.type_signatures,
            function_signatures=self.function_signatures,
            locals_signatures=self.locals_signatures,

            identifiers=self.identifiers,
            byte_array_pool=self.byte_array_pool,
            address_pool=self.address_pool,

            struct_defs=[],
            field_defs=[],
            function_defs=[self.main],
        )


# A `CompiledModule` defines the structure of a module which is the unit of published code.
#
# A `CompiledModule` contains a definition of types (with their fields) and functions.
# It is a unit of code that can be used by transactions or other modules.
#
# A module is published as a single entry and it is retrieved as a single blob.
#[derive(Clone, Debug, Eq, PartialEq)]
@dataclass
class CompiledModule:
    v0: CompiledModuleMut

    # By convention, the index of the module being implemented is 0.
    IMPLEMENTED_MODULE_INDEX: Uint16 = 0

    #impl ModuleAccess for CompiledModule:
    def as_module(self) -> CompiledModule:
        return self

    # Returns a reference to the inner `CompiledModuleMut`.
    def as_inner(self) -> CompiledModuleMut:
        return self.v0

    # Converts this instance into the inner `CompiledModuleMut`. Converting back to a
    # `CompiledModule` would require it to be verified again.
    def into_inner(self) -> CompiledModuleMut:
        return self.v0

    # Returns the number of items of a specific `IndexKind`.
    def kind_count(self, kind: IndexKind) -> usize:
        return self.as_inner().kind_count(kind)

    # Returns the code key of `module_handle`
    def module_id_for_handle(self, module_handle: ModuleHandle) -> ModuleId:
        return ModuleId(
            self.address_at(module_handle.address),
            deepcopy(self.identifier_at(module_handle.name)),
        )


    # Returns the code key of `self`
    def self_id(self) -> ModuleId:
        return self.module_id_for_handle(self.self_handle())


    # This function should only be called on an instance of CompiledModule obtained by invoking
    # into_module on some instance of CompiledScript. This function is the inverse of
    # into_module, i.e., script.into_module().into_script() == script.
    def into_script(self) -> CompiledScript:
        inner = self.into_inner()
        main = inner.function_defs.pop(0)
        return CompiledScript(CompiledScriptMut(
            module_handles=inner.module_handles,
            struct_handles=inner.struct_handles,
            function_handles=inner.function_handles,

            type_signatures=inner.type_signatures,
            function_signatures=inner.function_signatures,
            locals_signatures=inner.locals_signatures,

            identifiers=inner.identifiers,
            byte_array_pool=inner.byte_array_pool,
            address_pool=inner.address_pool,

            main=main
        ))


# A mutable version of `CompiledModule`. Converting to a `CompiledModule` requires this to pass
# the bounds checker.
@dataclass
class CompiledModuleMut:
    # Handles to external modules and self at position 0.
    module_handles: List[ModuleHandle]
    # Handles to external and internal types.
    class_handles: List[StructHandle]
    # Handles to external and internal functions.
    function_handles: List[FunctionHandle]

    # Type pool. A definition for all types used in the module.
    type_signatures: TypeSignaturePool
    # Function signature pool. Represents all function signatures defined or used in
    # the module.
    function_signatures: FunctionSignaturePool
    # Locals signature pool. The signature for all locals of the functions defined in
    # the module.
    locals_signatures: LocalsSignaturePool

    # All identifiers used in this module.
    identifiers: IdentifierPool
    # ByteArray pool. The byte array literals used in the module.
    byte_array_pool: ByteArrayPool
    # Address pool. The address literals used in the module. Those include literals for
    # code references (`ModuleHandle`).
    address_pool: AddressPool

    # Types defined in this module.
    class_defs: List[StructDefinition]
    # Fields defined on types in this module.
    field_defs: List[FieldDefinition]
    # Function defined in this module.
    function_defs: List[FunctionDefinition]


    # Returns the count of a specific `IndexKind`
    def kind_count(self, kind: IndexKind) -> usize:
        if kind == IndexKind.ModuleHandle:
            return self.module_handles.__len__()
        elif kind == IndexKind.StructHandle:
            return self.struct_handles.__len__()
        elif kind == IndexKind.FunctionHandle:
            return self.function_handles.__len__()
        elif kind == IndexKind.StructDefinition:
            return self.struct_defs.__len__()
        elif kind == IndexKind.FieldDefinition:
            return self.field_defs.__len__()
        elif kind == IndexKind.FunctionDefinition:
            return self.function_defs.__len__()
        elif kind == IndexKind.TypeSignature:
            return self.type_signatures.__len__()
        elif kind == IndexKind.FunctionSignature:
            return self.function_signatures.__len__()
        elif kind == IndexKind.LocalsSignature:
            return self.locals_signatures.__len__()
        elif kind == IndexKind.Identifier:
            return self.identifiers.__len__()
        elif kind == IndexKind.ByteArrayPool:
            return self.byte_array_pool.__len__()
        elif kind == IndexKind.AddressPool:
            return self.address_pool.__len__()
        else:
            bail("invalid kind for count: {}", other)

    # Converts this instance into `CompiledModule` after verifying it for basic internal
    # consistency. This includes bounds checks but no others.
    def freeze(self) -> CompiledModule:
        errors = BoundsChecker(self).verify()
        if not errors:
            return CompiledModule(self)
        else:
            raise VMException(errors)

    def check_field_range(
        self,
        field_count: MemberCount,
        first_field: FieldDefinitionIndex,
    ) -> None:
        first_field = first_field.into_index()
        field_count = int(field_count)
        # Both first_field and field_count are Uint16 so this is guaranteed to not overflow.
        # Note that last_field is exclusive, i.e. fields are in the range
        # [first_field, last_field).
        last_field = first_field + field_count
        if last_field > self.field_defs.__len__():
            msg = "Field definition range [{},{}) out of range for {}".format(
                first_field,
                last_field,
                self.field_defs.__len__()
            )
            status = VMStatus(StatusCode.RANGE_OUT_OF_BOUNDS)
            status.message = msg
            raise VMException([status])
        else:
            return None





# Return the simplest module that will pass the bounds checker
def empty_module() -> CompiledModuleMut:
    return CompiledModuleMut(
        module_handles=[ModuleHandle(
            address=AddressPoolIndex(0),
            name=IdentifierIndex(0),
        )],
        address_pool=[b'\x00'*32],
        identifiers=[self_module_name()],
        function_defs=[],
        struct_defs=[],
        field_defs=[],
        struct_handles=[],
        function_handles=[],
        type_signatures=[],
        function_signatures=[],
        locals_signatures=[LocalsSignature([])],
        byte_array_pool=[],
    )


# Create the following module which is convenient in tests:
# # module <SELF> {
# #     class Bar { x: Uint64 }
# //
# #     foo() {
# #     }
# # }
def basic_test_module() -> CompiledModuleMut:
    m = empty_module()

    m.function_signatures.append(FunctionSignature(
        return_types=[],
        arg_types=[],
        type_formals=[],
    ))

    m.function_handles.append(FunctionHandle(
        module=ModuleHandleIndex(0),
        name=IdentifierIndex(m.identifiers.__len__()),
        signature=FunctionSignatureIndex(0),
    ))
    m.identifiers.append("foo")

    m.function_defs.append(FunctionDefinition(
        function=FunctionHandleIndex(0),
        flags=0,
        acquires_global_resources=[],
        code=CodeUnit(
            max_stack_size=0,
            locals=LocalsSignatureIndex(0),
            code=[],
        ),
    ))

    m.struct_handles.append(StructHandle(
        module=ModuleHandleIndex(0),
        name=IdentifierIndex.new(m.identifiers.__len__()),
        is_nominal_resource=False,
        type_formals=[],
    ))
    m.identifiers.append("Bar")

    m.struct_defs.append(StructDefinition(
        struct_handle=StructHandleIndex(0),
        field_information=StructFieldInformation.Declared(
            field_count=1,
            fields=FieldDefinitionIndex(0),
        ),
    ))

    m.field_defs.append(FieldDefinition(
        struct_=StructHandleIndex(0),
        name=IdentifierIndex(m.identifiers.__len__()),
        signature=TypeSignatureIndex(0),
    ))
    m.identifiers.append("x")
    m.type_signatures.append(TypeSignature(SignatureToken.U64))
    return m


# Create a dummy module to wrap the bytecode program in local@code
def dummy_procedure_module(code: List[Bytecode]) -> CompiledModule:
    module = empty_module()
    code_unit = CodeUnit()
    code_unit.code = code
    fun_def = FunctionDefinition()
    fun_def.code = code_unit

    module.function_signatures.append(FunctionSignature(
        arg_types=[],
        return_types=[],
        type_formals=[],
    ))
    fun_handle = FunctionHandle(
        module=ModuleHandleIndex(0),
        name=IdentifierIndex(0),
        signature=FunctionSignatureIndex(0),
    )

    module.function_handles.append(fun_handle)
    module.function_defs.append(fun_def)
    return module.freeze()


# Return a simple script that contains only a return in the main()
def empty_script() -> CompiledScriptMut:
    default_address = b'\x03'*32
    self_module_name = self_module_name()
    main_name = "main"
    void_void_sig = FunctionSignature(
        arg_types=[],
        return_types=[],
        type_formals=[],
    )
    no_args_no_locals = LocalsSignature([])
    self_module_handle = ModuleHandle(
        address=AddressPoolIndex(0),
        name=IdentifierIndex(0),
    )
    main = FunctionHandle(
        module=ModuleHandleIndex(0),
        name=IdentifierIndex(1),
        signature=FunctionSignatureIndex(0),
    )
    code = CodeUnit(
        max_stack_size=1,
        locals=LocalsSignatureIndex(0),
        code=[Bytecode.Ret],
    )
    main_def = FunctionDefinition(
        function=FunctionHandleIndex(0),
        flags=CodeUnit.PUBLIC,
        acquires_global_resources=[],
        code=code
    )
    return CompiledScriptMut(
        module_handles=[self_module_handle],
        struct_handles=[],
        function_handles=[main],

        type_signatures=[],
        function_signatures=[void_void_sig],
        locals_signatures=[no_args_no_locals],

        identifiers=[self_module_name, main_name],
        byte_array_pool=[],
        address_pool=[default_address],
        main=main_def,
    )
