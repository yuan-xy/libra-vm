from __future__ import annotations
from move_ir.types.location import *
from libra.account_address import Address
from libra.language_storage import ModuleId
from move_core.types.identifier import Identifier
from libra_vm.file_format import CodeUnit
from libra_vm.file_format_common import Opcodes, SerializedType
from typing import List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from enum import IntEnum


# A set of move modules and a Move transaction script
@dataclass
class Program:
    # The modules to publish
    modules: List[ModuleDefinition]
    # The transaction script to execute
    script: Script



# A script or a module, used to represent the two types of transactions.
@dataclass
class ScriptOrModule:
    tag: int
    value: Union[Script, ModuleDefinition]

    SCRIPT = 1
    MODULE = 2


def get_external_deps(imports: List[ImportDefinition]) -> List[ModuleId]:
    deps = set()
    for dep in imports:
        if dep.ident.tag == ModuleIdent.QUALIFIED:
            aid = dep.ident.value
            identifier = aid.name
            deps.add(ModuleId(aid.address, identifier))
    return list(deps)


# The move transaction script to be executed
@dataclass
class Script:
    # The dependencies of `main`, i.e. of the transaction script
    imports: List[ImportDefinition]
    # Explicit declaration of dependencies. If not provided, will be inferred based on given
    # dependencies to the IR compiler
    explicit_dependency_declarations: List[ModuleDependency]
    # The transaction script's `main` procedure
    main: Function

    def __iter__(self):
        return self

    def __next__(self) -> Statement:
        func_body = self.main.value.body
        if isinstance(func_body, FunctionBodyMove):
            return func_body.code.stmts.pop(0)
        else:
            bail("main() is not a move function.")

    def __eq__(self, other: Script) -> bool:
        return self.imports == other.imports and self.main.value.body == other.main.value.body


    # Accessor for the body of the 'main' procedure
    def body(self) -> Block_:
        func_body = self.main.value.body
        if isinstance(func_body, FunctionBodyMove):
            return func_body.code
        if isinstance(func_body, FunctionBodyBytecode):
            bail("Invalid body access on bytecode main()")
        if isinstance(func_body, FunctionBodyNative):
            bail("main() cannot be native")
        bail("unreachable!")


    # Return a vector of `ModuleId` for the external dependencies.
    def get_external_deps(self) -> List[ModuleId]:
        return get_external_deps(self.imports)


class MyStr(str):
    @classmethod
    def new(cls, s: str):
        return cls(s)

# Newtype for a name of a module
class ModuleName(MyStr):
    pass

SELF_MODULE_NAME: ModuleName = "Self"


# Newtype of the address + the module name
@dataclass
class QualifiedModuleIdent:
    # Name for the module. Will be unique among modules published under the same address
    name: ModuleName
    # Address that this module is published under
    address: Address

    def __hash__(self):
        return (self.name, self.address).__hash__()


# A Move module
@dataclass
class ModuleDefinition:
    # name of the module
    name: ModuleName
    # the module's dependencies
    imports: List[ImportDefinition]
    # Explicit declaration of dependencies. If not provided, will be inferred based on given
    # dependencies to the IR compiler
    explicit_dependency_declarations: List[ModuleDependency]
    # the structs (including resources) that the module defines
    structs: List[StructDefinition]
    # the procedure that the module defines
    functions: List[(FunctionName, Function)]
    # the synthetic, specification variables the module defines.
    synthetics: List[SyntheticDefinition]


    # Return a vector of `ModuleId` for the external dependencies.
    def get_external_deps(self) -> List[ModuleId]:
        return get_external_deps(self.imports)



# Either a qualified module name like `addr.m` or `Transaction.m`, which refers to a module in
# the same transaction.
@dataclass
class ModuleIdent:
    tag: int
    value: Union[ModuleName, QualifiedModuleIdent]

    TRANSACTION = 1
    QUALIFIED = 2

    @classmethod
    def Transaction(cls, v: ModuleName):
        return cls(ModuleIdent.TRANSACTION, v)

    @classmethod
    def Qualified(cls, v: QualifiedModuleIdent):
        return cls(ModuleIdent.QUALIFIED, v)

    def name(self) -> ModuleName:
        if self.tag == ModuleIdent.TRANSACTION:
            return self.value
        else:
            return self.value.name


# Explicitly given dependency
@dataclass
class ModuleDependency:
    # Qualified identifer of the dependency
    name: ModuleName
    # The structs (including resources) that the dependency defines
    structs: List[StructDependency]
    # The signatures of functions that the dependency defines
    functions: List[FunctionDependency]



# A dependency/import declaration
@dataclass
class ImportDefinition:
    # the dependency
    # `addr.m` or `Transaction.m`
    ident: ModuleIdent
    # the alias for that dependency
    alias: ModuleName

    # Creates a new import definition from a module identifier and an optional alias
    # If the alias is `None`, the alias will be a cloned copy of the identifiers module name
    @classmethod
    def new(cls, ident: ModuleIdent, alias_opt: Optional[ModuleName]) -> ImportDefinition:
        if alias_opt is None:
            alias = ident.name()
        else:
            alias = alias_opt
        return cls(ident, alias)



# Newtype for a variable/local
class Var_(MyStr):
    pass

# The type of a variable with a location
class Var(Spanned):
    T = Var_


# New type that represents a type variable. Used to declare type formals & reference them.
class TypeVar_(MyStr):
    pass

# The type of a type variable with a location.
class TypeVar(Spanned):
    T = TypeVar_



# TODO: This enum is completely equivalent to vm.file_format.Kind.
#       Should we just use vm.file_format.Kind or replace both with a common one
# The kind of a type. Analogous to `vm.file_format.Kind`.
class Kind(IntEnum):
    All = 1
    Resource = 3
    Unrestricted =2


# The type of a single value
@dataclass
class Type:
    tag: SerializedType #NO MUTABLE_REFERENCE
    # MOVE user type, resource or unrestricted
    struct : Tuple[QualifiedStructIdent, List[Type]] = None
    # (Mutable) Reference to a type.
    reference : Tuple[bool, Type] = None
    # Type parameter.
    typeParameter : TypeVar_ = None
    vector_type: Type = None


    @classmethod
    def Vector(cls, v):
        return cls(SerializedType.VECTOR, vector_type=v)

    @classmethod
    def Struct(cls, v):
        return cls(SerializedType.STRUCT, struct=v)

    @classmethod
    def Reference(cls, v):
        return cls(SerializedType.REFERENCE, reference=v)

    @classmethod
    def TypeParameter(cls, v):
        return cls(SerializedType.TYPE_PARAMETER, typeParameter=v)



# Identifier for a struct definition. Tells us where to look in the storage layer to find the
# code associated with the interface
@dataclass
class QualifiedStructIdent:
    # Module name and address in which the struct is contained
    module: ModuleName
    # Name for the struct class. Should be unique among structs published under the same
    # module+address
    name: StructName

    def __hash__(self):
        return (self.module, self.name).__hash__()


# The field newtype
class Field_(MyStr):
    pass

# A field coupled with source location information
class Field(Spanned):
    T = Field_


# A field map
Fields = List[Tuple[Field, Any]]
TypeFields = List[Tuple[Field, Type]]
VarFields = List[Tuple[Field, Var]]

# Newtype for the name of a struct
class StructName(MyStr):
    pass

# A Move struct
@dataclass
class StructDefinition_:
    # The struct will have kind resource if `is_nominal_resource` is True
    # and will be dependent on it's type arguments otherwise
    is_nominal_resource: bool
    # Human-readable name for the struct that also serves as a nominal type
    name: StructName
    # Kind constraints of the type parameters
    type_formals: List[Tuple[TypeVar, Kind]]
    # the fields each instance has
    fields: StructDefinitionFields
    # the invariants for this struct
    invariants: List[Invariant]

    # Creates a new StructDefinition from the resource kind (True if resource), the string
    # representation of the name, and the user specified fields, a map from their names to their
    # types
    # Does not verify the correctness of any internal properties, e.g. doesn't check that the
    # fields do not have reference types
    @classmethod
    def move_declared(cls,
        is_nominal_resource: bool,
        name: str,
        type_formals: List[Tuple[TypeVar, Kind]],
        fields: TypeFields,
        invariants: List[Invariant],
    ) -> StructDefinition_:
        return cls(
            is_nominal_resource,
            name,
            type_formals,
            StructDefinitionFields.Move(fields),
            invariants,
        )


    # Creates a new StructDefinition from the resource kind (True if resource), the string
    # representation of the name, and the user specified fields, a map from their names to their
    # types
    @classmethod
    def native(cls,
        is_nominal_resource: bool,
        name: str,
        type_formals: List[Tuple[TypeVar, Kind]],
    ) -> StructDefinition_:
        return cls(
            is_nominal_resource,
            name,
            type_formals,
            StructDefinitionFields.Native(),
            [],
        )


# The type of a StructDefinition along with its source location information
class StructDefinition(Spanned):
    T = StructDefinition_



# An explicit struct dependency
@dataclass
class StructDependency:
    # The struct will have kind resource if `is_nominal_resource` is True
    # and will be dependent on it's type arguments otherwise
    is_nominal_resource: bool
    # Human-readable name for the struct that also serves as a nominal type
    name: StructName
    # Kind constraints of the type parameters
    type_formals: List[Tuple[TypeVar, Kind]]


# The fields of a Move struct
@dataclass
class StructDefinitionFields:
    tag: int
    fields: TypeFields = None

    # The fields are declared
    MOVE = 1
    # The struct is a type provided by the VM
    NATIVE = 2

    @classmethod
    def Move(cls, fields):
        return cls(StructDefinitionFields.MOVE, fields)

    @classmethod
    def Native(cls):
        return cls(StructDefinitionFields.NATIVE)



# Newtype for the name of a function
class FunctionName(MyStr):
    pass

# The signature of a function
@dataclass
class FunctionSignature:
    # Possibly-empty list of (formal name, formal type) pairs. Names are unique.
    formals: List[Tuple[Var, Type]]
    # Optional return types
    return_type: List[Type]
    # Possibly-empty list of Tuple[TypeVar, Kind] pairs.s.
    type_formals: List[Tuple[TypeVar, Kind]]


# An explicit function dependency
@dataclass
class FunctionDependency:
    # Name of the function dependency
    name: FunctionName
    # Signature of the function dependency
    signature: FunctionSignature


# Public or internal modifier for a procedure
class FunctionVisibility(IntEnum):
    # The procedure can be invoked anywhere
    # `public`
    Public = CodeUnit.PUBLIC
    # The procedure can be invoked only internally
    # `<no modifier>`
    Internal = 0


# The body of a Move function
class FunctionBody:
    pass


@dataclass
class FunctionBodyMove:
    # The body is declared
    # `locls` are all of the declared locls
    # `code` is the code that defines the procedure
    locls: List[Tuple[Var, Type]]
    code: Block_


@dataclass
class FunctionBodyBytecode:
    locls: List[Tuple[Var, Type]]
    code: BytecodeBlocks


class FunctionBodyNative:
    # The body is provided by the runtime
    pass


# A Move function/procedure
@dataclass
class Function_:
    # The visibility (public or internal)
    visibility: FunctionVisibility
    # The type signature
    signature: FunctionSignature
    # List of nominal resources (declared in this module) that the procedure might access
    # Either through: BorrowGlobal, MoveFrom, or transitively through another procedure
    # This list of acquires grants the borrow checker the ability to statically verify the safety
    # of references into global storage
    acquires: List[StructName]
    # List of specifications for the Move prover (experimental)
    specifications: List[Condition]
    # The code for the procedure
    body: FunctionBody

    # Creates a new function declaration from the components of the function
    # See the declaration of the struct `Function` for more details
    @classmethod
    def new(cls,
        visibility: FunctionVisibility,
        formals: List[Tuple[Var, Type]],
        return_type: List[Type],
        type_formals: List[Tuple[TypeVar, Kind]],
        acquires: List[StructName],
        specifications: List[Condition],
        body: FunctionBody,
    ) -> Function_:
        signature = FunctionSignature(formals, return_type, type_formals)
        return cls(
            visibility,
            signature,
            acquires,
            specifications,
            body,
        )


# The type of a Function coupled with its source location information.
class Function(Spanned):
    T = Function_



# Builtin "function"-like operators that often have a signature not expressable in the
# type system and/or have access to some runtime/storage context
class BuiltinTag(IntEnum):
    # Check if there is a struct object (`StructName` resolved by current module) associated with
    # the given address
    Exists = 1
    # Get a reference to the resource(`StructName` resolved by current module) associated
    # with the given address
    BorrowGlobal = 2
    # Returns the address of the current transaction's sender
    GetTxnSender = 3

    # Remove a resource of the given type from the account with the given address
    MoveFrom = 4
    # Publish an instantiated struct object into sender's account.
    MoveToSender = 5

    # Convert a mutable reference into an immutable one
    Freeze = 6

    # Cast an integer into Uint8.
    ToU8 = 7
    # Cast an integer into Uint64.
    ToU64 = 8
    # Cast an integer into Uint128.
    ToU128 = 9



@dataclass
class Builtin:
    tag: BuiltinTag

    # Check if there is a struct object (`StructName` resolved by current module) associated with
    # the given address
    exists: Tuple[StructName, List[Type]] = None
    # Get a reference to the resource(`StructName` resolved by current module) associated
    # with the given address
    borrow: Tuple[bool, StructName, List[Type]] = None

    # Remove a resource of the given type from the account with the given address
    move: Tuple[StructName, List[Type]] = None
    # Publish an instantiated struct object into sender's account.


@dataclass
class ModuleFunctionCall:
    module: ModuleName
    name: FunctionName
    type_actuals: List[Type]


# Enum for different function calls
@dataclass
class FunctionCall_:
    tag: int
    value: Union[Builtin, ModuleFunctionCall]

    BUILTIN = 1
    MODULE_FUNCTION_CALL = 2

    # functions defined in the host environment
    @classmethod
    def Builtin(cls, v: Builtin):
        return cls(FunctionCall_.BUILTIN, v)

    # The call of a module defined procedure
    @classmethod
    def ModuleFunctionCall(cls, v: ModuleFunctionCall):
        return cls(FunctionCall_.MODULE_FUNCTION_CALL, v)

    # Creates a `FunctionCall.ModuleFunctionCall` variant
    @classmethod
    def module_call(cls, module: ModuleName, name: FunctionName, type_actuals: List[Type]) -> FunctionCall_:
        mfc = ModuleFunctionCall(
            module,
            name,
            type_actuals,
        )
        return cls.ModuleFunctionCall(mfc)

    # Creates a `FunctionCall.Builtin` variant with no location information
    @classmethod
    def builtin(cls, bif: Builtin) -> FunctionCall:
        return Spanned.unsafe_no_loc(FunctionCall_.Builtin(bif))



# The type for a function call and its location
class FunctionCall(Spanned):
    T = FunctionCall_

# Enum for Move lvalues
@dataclass
class LValue_:
    tag: int
    value: Union[Var, Exp, None]

    VAR = 1
    MUTATE = 2
    POP = 3

    # `x`
    @classmethod
    def Var(cls, v: Var):
        return cls(LValue_.VAR, v)
    # `*e`
    @classmethod
    def Mutate(cls, v:Exp):
        return cls(LValue_.MUTATE, v)
    # `_`
    @classmethod
    def Pop(cls):
        return cls(LValue_.POP, None)


class LValue(Spanned):
    T = LValue_


# Enum for Move commands
class CmdTag(IntEnum):
    # `l_1, ..., l_n = e`
    Assign = 1
    # `n { f_1: x_1, ... , f_j: x_j  } = e`
    Unpack = 2
    # `abort e`
    Abort = 3
    # `return e_1, ... , e_j`
    Return = 4
    # `break`
    Break = 5
    # `continue`
    Continue = 6

    Exp = 7


# Enum for Move commands
@dataclass
class Cmd_:
    tag: CmdTag
    value: Any = None

    # `l_1, ..., l_n = e`
    @classmethod
    def Assign(cls, v: Tuple[List[LValue], Exp]):
        return cls(CmdTag.Assign, v)

    # `n { f_1: x_1, ... , f_j: x_j  } = e`
    @classmethod
    def Unpack(cls, v: Tuple[StructName, List[Type], VarFields, Exp]):
        return cls(CmdTag.Unpack, v)

    # `abort e`
    @classmethod
    def Abort(cls, v: Optional[Exp]):
        return cls(CmdTag.Abort, v)

    # `return e_1, ... , e_j`
    @classmethod
    def Return(cls, v: Exp):
        return cls(CmdTag.Return, v)

    @classmethod
    def Exp(cls, v: Exp):
        return cls(CmdTag.Exp, v)

    @classmethod
    def Break(cls):
        return cls(CmdTag.Break)

    @classmethod
    def Continue(cls):
        return cls(CmdTag.Continue)

    # Creates a command that returns no values
    @classmethod
    def return_empty(cls) -> Cmd_:
        return Cmd_(CmdTag.Return, Spanned.unsafe_no_loc(ExprListExp([])))


    # Creates a command that returns a single value
    @classmethod
    def return_(cls, op: Exp) -> Cmd_:
        return Cmd_(CmdTag.Return, op)


# The type of a command with its location
class Cmd(Spanned):
    T = Cmd_


# Struct defining an if statement
@dataclass
class IfElse:
    # the if's condition
    cond: Exp
    # the block taken if the condition is `True`
    if_block: Block
    # the block taken if the condition is `False`
    else_block: Optional[Block] = None

    # Creates an if-statement with no else branch
    @classmethod
    def if_block(cls, cond: Exp, if_block: Block) -> IfElse:
        return IfElse(cond, if_block, None)


    # Creates an if-statement with an else branch
    @classmethod
    def if_else(cls, cond: Exp, if_block: Block, else_block: Block) -> IfElse:
        return IfElse(cond, if_block, else_block)


# Struct defining a while statement
@dataclass
class While:
    # The condition for a while statement
    cond: Exp
    # The block taken if the condition is `True`
    block: Block


# Struct defining a loop statement
@dataclass
class Loop:
    # The body of the loop
    block: Block


class Statement:
    # Lifts a command into a statement
    @classmethod
    def cmd(cls, c: Cmd):
        return CommandStatement(c)


    # Creates an `Statement.IfElseStatement` variant with no else branch
    @classmethod
    def if_block(cls, cond: Exp, if_block: Block):
        return IfElseStatement(IfElse.if_block(cond, if_block))


    # Creates an `Statement.IfElseStatement` variant with an else branch
    @classmethod
    def if_else(cls, cond: Exp, if_block: Block, else_block: Block):
        return IfElseStatement(IfElse.if_else(cond, if_block, else_block))


@dataclass
class CommandStatement(Statement):
    # `c;`
    v0: Cmd


@dataclass
class IfElseStatement(Statement):
    # `if (e) { s_1 else: s_2 }`
    v0: IfElse


@dataclass
class WhileStatement(Statement):
    # `while (e) { s }`
    v0: While


@dataclass
class LoopStatement(Statement):
    # `loop { s }`
    v0: Loop


@dataclass
class EmptyStatement(Statement):
    # no-op that eases parsing in some places
    pass



# `{ s }`
@dataclass
class Block_:
    # The statements that make up the block
    stmts: List[Statement]

    # Creates an empty block
    @classmethod
    def empty(cls) -> Block_:
        return cls([])

    def __iter__(self):
        return self

    def __next__(self) -> Statement:
        return self.stmts.pop(0)

# The type of a Block coupled with source location information.
class Block(Spanned):
    T = Block_


# Bottom of the value hierarchy. These values can be trivially copyable and stored in statedb as a
# single entry.
@dataclass
class CopyableVal_:
    tag: SerializedType
    value: Any

    # # An address in the global storage
    # Address(Address),
    # # An unsigned 8-bit integer
    # U8(Uint8),
    # # An unsigned 64-bit integer
    # U64(Uint64),
    # # An unsigned 128-bit integer
    # U128(Uint128),
    # # True or False
    # Bool(bool),
    # # `b"<bytes>"`
    # ByteArray(ByteArray),


# The type of a value and its location
class CopyableVal(Spanned):
    T = CopyableVal_


# Enum for unary operators
class UnaryOp(IntEnum):
    # Boolean negation
    Not = 1


# Enum for binary operators
class BinOp(IntEnum):
    # Uint64 ops
    # `+`
    Add = 1
    # `-`
    Sub = 2
    # `*`
    Mul = 3
    # `%`
    Mod = 4
    # `/`
    Div = 5
    # `|`
    BitOr = 6
    # `&`
    BitAnd = 7
    # `^`
    Xor = 8
    # `<<`
    Shl = 9
    # `>>`
    Shr = 10

    # Bool ops
    # `&&`
    And = 11
    # `||`
    Or = 12

    # Compare Ops
    # `==`
    Eq = 13
    # `!=`
    Neq = 14
    # `<`
    Lt = 15
    # `>`
    Gt = 16
    # `<=`
    Le = 17
    # `>=`
    Ge = 18
    # '..'  only used in specs
    Subrange = 19


# Enum for all expressions
class Exp_:
    pass
    # # Creates a new address `Exp` with no location information
    # def address(addr: Address) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Value(Spanned.unsafe_no_loc(CopyableVal_.Address(
    #         addr,
    #     ))))
    # }

    # # Creates a new value `Exp` with no location information
    # def value(b: CopyableVal_) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Value(Spanned.unsafe_no_loc(b)))
    # }

    # # Creates a new Uint64 `Exp` with no location information
    # def Uint64(i: Uint64) -> Exp {
    #     Exp_.value(CopyableVal_.U64(i))
    # }

    # # Creates a new bool `Exp` with no location information
    # def bool(b: bool) -> Exp {
    #     Exp_.value(CopyableVal_.Bool(b))
    # }

    # # Creates a new bytearray `Exp` with no location information
    # def byte_array(buf: ByteArray) -> Exp {
    #     Exp_.value(CopyableVal_.ByteArray(buf))
    # }

    # # Creates a new pack/struct-instantiation `Exp` with no location information
    # def instantiate(n: StructName, tys: List[Type], s: ExpFields) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Pack(n, tys, s))
    # }

    # # Creates a new binary operator `Exp` with no location information
    # def binop(lhs: Exp, op: BinOp, rhs: Exp) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.BinopExp(Box.new(lhs), op, Box.new(rhs)))
    # }

    # # Creates a new `e+e` `Exp` with no location information
    # def add(lhs: Exp, rhs: Exp) -> Exp {
    #     Exp_.binop(lhs, BinOp.Add, rhs)
    # }

    # # Creates a new `e-e` `Exp` with no location information
    # def sub(lhs: Exp, rhs: Exp) -> Exp {
    #     Exp_.binop(lhs, BinOp.Sub, rhs)
    # }

    # # Creates a new `*e` `Exp` with no location information
    # def dereference(e: Exp) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Dereference(Box.new(e)))
    # }

    # # Creates a new borrow field `Exp` with no location information
    # def borrow(is_mutable: bool, exp: Exp, field: Field_) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Borrow {
    #         is_mutable,
    #         exp,
    #         field,
    #     })
    # }

    # # Creates a new copy-local `Exp` with no location information
    # def copy(v: Var) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Copy(v))
    # }

    # # Creates a new move-local `Exp` with no location information
    # def move_(v: Var) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.Move(v))
    # }

    # # Creates a new function call `Exp` with no location information
    # def function_call(f: FunctionCall, e: Exp) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.FunctionCall(f, Box.new(e)))
    # }

    # def expr_list(exps: List[Exp]) -> Exp {
    #     Spanned.unsafe_no_loc(Exp_.ExprList(exps))
    # }

@dataclass
class DereferenceExp(Exp_):
    # `*e`
    v0: Exp

@dataclass
class UnaryExp(Exp_):
    # `op e`
    v0: Tuple[UnaryOp, Exp]

@dataclass
class BinopExp(Exp_):
    # `e_1 op e_2`
    v0: Tuple[Exp, BinOp, Exp]

@dataclass
class ValueExp(Exp_):
    # Wrapper to lift `CopyableVal` into `Exp`
    # `v`
    v0: CopyableVal

@dataclass
class PackExp(Exp_):
    # Takes the given field values and instantiates the struct
    # Returns a fresh `StructInstance` whose type and kind (resource or otherwise)
    # as the current struct(i.e., the struct of the method we're currently executing).
    # `n { f_1: e_1, ... , f_j: e_j }`
    v0: Tuple[StructName, List[Type], ExpFields]

@dataclass
class BorrowExp(Exp_):
    # `&e.f`, `e.f`
    # mutable or not
    is_mutable: bool
    # the expression containing the reference
    exp: Exp
    # the field being borrowed
    field: Field_

@dataclass
class MoveExp(Exp_):
    # `move(x)`
    v0: Var

@dataclass
class CopyExp(Exp_):
    # `copy(x)`
    v0: Var

@dataclass
class BorrowLocalExp(Exp_):
    # `&x` or `x`
    v0: Tuple[bool, Var]

@dataclass
class FunctionCallExp(Exp_):
    # `f(e)` or `f(e_1, e_2, ..., e_j)`
    v0: Tuple[FunctionCall, Exp]

@dataclass
class ExprListExp(Exp_):
    # (e_1, e_2, e_3, ..., e_j)
    v0: List[Exp]


# The type for a `Exp_` and its location
class Exp(Spanned):
    T = Exp_


# The type for fields and their bound expressions
ExpFields = List[Tuple[Field, Exp]]


@dataclass
class Bytecode_:
    tag: Opcodes
    value: Any

    # Pop,
    # Ret,
    # BrTrue(Label),
    # BrFalse(Label),
    # Branch(Label),
    # LdU8(Uint8),
    # LdU64(Uint64),
    # LdU128(Uint128),
    # CastU8,
    # CastU64,
    # CastU128,
    # LdByteArray(ByteArray),
    # LdAddr(Address),
    # LdTrue,
    # LdFalse,
    # CopyLoc(Var),
    # MoveLoc(Var),
    # StLoc(Var),
    # Call(ModuleName, FunctionName, List[Type]),
    # Pack(StructName, List[Type]),
    # Unpack(StructName, List[Type]),
    # ReadRef,
    # WriteRef,
    # FreezeRef,
    # MutBorrowLoc(Var),
    # ImmBorrowLoc(Var),
    # MutBorrowField(StructName, Field),
    # ImmBorrowField(StructName, Field),
    # MutBorrowGlobal(StructName, List[Type]),
    # ImmBorrowGlobal(StructName, List[Type]),
    # Add,
    # Sub,
    # Mul,
    # Mod,
    # Div,
    # BitOr,
    # BitAnd,
    # Xor,
    # Or,
    # And,
    # Not,
    # Eq,
    # Neq,
    # Lt,
    # Gt,
    # Le,
    # Ge,
    # Abort,
    # GetTxnSenderAddress,
    # Exists(StructName, List[Type]),
    # MoveFrom(StructName, List[Type]),
    # MoveToSender(StructName, List[Type]),
    # Shl,
    # Shr,

class Bytecode(Spanned):
    T = Bytecode_

class Label(MyStr):
    pass

BytecodeBlock = List[Bytecode]
BytecodeBlocks = List[Tuple[Label, BytecodeBlock]]






"""
impl fmt.Display for TypeVar_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for Kind {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "{}",
            match self {
                Kind.All => "all",
                Kind.Resource => "resource",
                Kind.Unrestricted => "unrestricted",
            }
        )
    }
}

impl fmt.Display for ScriptOrModule {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        use ScriptOrModule.*
        match self {
            Module(module_def) => write!(f, "{}", module_def),
            Script(script) => write!(f, "{}", script),
        }
    }
}

impl fmt.Display for Script {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        writeln!(f, "Script(")
        write!(f, "Imports(")
        write!(f, "{}", intersperse(self.imports, ", "))
        writeln!(f, ")")
        write!(f, "Main(")
        write!(f, "{}", self.main)
        write!(f, ")")
        write!(f, ")")
    }
}

impl fmt.Display for ModuleIdent {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        use ModuleIdent.*
        match self {
            Transaction(module_name) => write!(f, "{}", module_name),
            Qualified(qual_module_ident) => write!(f, "{}", qual_module_ident),
        }
    }
}

impl fmt.Display for ModuleName {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for QualifiedModuleIdent {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}.{}", self.address, self.name)
    }
}

impl fmt.Display for ModuleDefinition {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        writeln!(f, "Module({}, ", self.name)

        writeln!(f, "Imports(")
        for import in self.imports {
            writeln!(f, "{};", import)
        }
        writeln!(f, ")")

        writeln!(f, "Dependency(")
        for dependency in self.explicit_dependency_declarations {
            writeln!(f, "{},", dependency)
        }
        writeln!(f, ")")

        writeln!(f, "Structs(")
        for struct_def in self.structs {
            writeln!(f, "{}, ", struct_def)
        }
        writeln!(f, ")")

        writeln!(f, "Functions(")
        for (fun_name, fun) in self.functions {
            writeln!(f, "({}, {}), ", fun_name, fun)
        }
        writeln!(f, ")")

        writeln!(f, ")")
    }
}

impl fmt.Display for ImportDefinition {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "import {} as {}", self.ident, self.alias)
    }
}

impl fmt.Display for ModuleDependency {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "Depedency({}, ", self.name)
        for sdep in self.structs {
            writeln!(f, "{}, ", sdep)
        }
        for fdep in self.functions {
            writeln!(f, "{}, ", fdep)
        }
        writeln!(f, ")")
    }
}

impl fmt.Display for StructDependency {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "StructDep({} {}{}",
            if self.is_nominal_resource {
                "resource"
            else:
                ""
            },
            self.name,
            format_type_formals(self.type_formals)
        )
    }
}

impl fmt.Display for FunctionDependency {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "FunctionDep({}{}", self.name, self.signature)
    }
}

impl fmt.Display for StructDefinition_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        writeln!(
            f,
            "Struct({}{}, ",
            self.name,
            format_type_formals(self.type_formals)
        )
        match self.fields {
            StructDefinitionFields.Move { fields } => writeln!(f, "{}", format_fields(fields))?,
            StructDefinitionFields.Native => writeln!(f, "{{native}}")?,
        }
        write!(f, ")")
    }
}

impl fmt.Display for Function_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{} ({})", self.signature, self.body)
    }
}

impl fmt.Display for Field_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for StructName {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for FunctionName {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for FunctionBody {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            FunctionBody.Move {
                ref locls,
                ref code,
            } => {
                for (local, ty) in locls {
                    write!(f, "{}: {};", local, ty)
                }
                writeln!(f, "{}", code)
            }
            FunctionBody.Bytecode { locls, code } => {
                write!(f, "locls: [")
                for (local, ty) in locls {
                    write!(f, "{}: {},", local, ty)
                }
                writeln!(f, "]")
                for (label, block) in code {
                    writeln!(f, "label {}:", &label.0)
                    for instr in block {
                        writeln!(f, "  {}", instr)
                    }
                }
                ()
            }
            FunctionBody.Native => write!(f, "native"),
        }
    }
}

# TODO: This function should take an iterator instead.
def intersperse<T: fmt.Display>(items: &[T], join: &str) -> String {
    # TODO: Any performance issues here? Could be O(n^2) if not optimized.
    items.iter().fold(String.new(), |acc, v| {
        format!("{acc}{join}{v}", acc = acc, join = join, v = v)
    })
}

def format_fields<T: fmt.Display>(fields: &[(Field, T)]) -> String {
    fields.iter().fold(String.new(), |acc, (field, val)| {
        format!("{} {}: {},", acc, field.value, val)
    })
}

impl fmt.Display for FunctionSignature {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", format_type_formals(self.type_formals))
        write!(f, "(")
        for (v, ty) in self.formals.iter() {
            write!(f, "{}: {}, ", v, ty)
        }
        write!(f, ")")
        ()
    }
}

impl fmt.Display for QualifiedStructIdent {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}.{}", self.module, self.name)
    }
}

def format_type_actuals(tys: &[Type]) -> String {
    if tys.is_empty() {
        "".to_string()
    else:
        format!("<{}>", intersperse(tys, ", "))
    }
}

def format_type_formals(formals: &[Tuple[TypeVar, Kind]]) -> String {
    if formals.is_empty() {
        "".to_string()
    else:
        formatted = formals
            .iter()
            .map(|(tv, k)| format!("{}: {}", tv.value, k))
            .collect.<List[_]>()
        format!("<{}>", intersperse(&formatted, ", "))
    }
}

impl fmt.Display for Type {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Type.U8 => write!(f, "Uint8"),
            Type.U64 => write!(f, "Uint64"),
            Type.U128 => write!(f, "Uint128"),
            Type.Bool => write!(f, "bool"),
            Type.Address => write!(f, "address"),
            Type.ByteArray => write!(f, "bytearray"),
            Type.Vector(ty) => write!(f, "vector<{}>", ty),
            Type.Struct(ident, tys) => write!(f, "{}{}", ident, format_type_actuals(tys)),
            Type.Reference(is_mutable, t) => {
                write!(f, "&{}{}", if *is_mutable { "mut " else: "" }, t)
            }
            Type.TypeParameter(s) => write!(f, "{}", s),
        }
    }
}

impl fmt.Display for Var_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "{}", self.0)
    }
}

impl fmt.Display for Builtin {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Builtin.Exists(t, tys) => write!(f, "exists<{}{}>", t, format_type_actuals(tys)),
            Builtin.BorrowGlobal(mut_, t, tys) => {
                mut_flag = if *mut_ { "_mut" else: "" }
                write!(
                    f,
                    "borrow_global{}<{}{}>",
                    mut_flag,
                    t,
                    format_type_actuals(tys)
                )
            }
            Builtin.GetTxnSender => write!(f, "get_txn_sender"),
            Builtin.MoveFrom(t, tys) => write!(f, "move_from<{}{}>", t, format_type_actuals(tys)),
            Builtin.MoveToSender(t, tys) => {
                write!(f, "move_to_sender<{}{}>", t, format_type_actuals(tys))
            }
            Builtin.Freeze => write!(f, "freeze"),
            Builtin.ToU8 => write!(f, "to_Uint8"),
            Builtin.ToU64 => write!(f, "to_Uint64"),
            Builtin.ToU128 => write!(f, "to_Uint128"),
        }
    }
}

impl fmt.Display for FunctionCall_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            FunctionCall_.Builtin(fun) => write!(f, "{}", fun),
            FunctionCall_.ModuleFunctionCall {
                module,
                name,
                type_actuals,
            } => write!(
                f,
                "{}.{}{}",
                module,
                name,
                format_type_actuals(type_actuals)
            ),
        }
    }
}

impl fmt.Display for LValue_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            LValue_.Var(x) => write!(f, "{}", x),
            LValue_.Mutate(e) => write!(f, "*{}", e),
            LValue_.Pop => write!(f, "_"),
        }
    }
}

impl fmt.Display for Cmd_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Cmd_.Assign(var_list, e) => {
                if var_list.is_empty() {
                    write!(f, "{};", e)
                else:
                    write!(f, "{} = ({});", intersperse(var_list, ", "), e)
                }
            }
            Cmd_.Unpack(n, tys, bindings, e) => write!(
                f,
                "{}{} {{ {} }} = {}",
                n,
                format_type_actuals(tys),
                bindings
                    .iter()
                    .fold(String.new(), |acc, (field, var)| format!(
                        "{} {} : {},",
                        acc, field, var
                    )),
                e
            ),
            Cmd_.Abort(None) => write!(f, "abort;"),
            Cmd_.Abort(Some(err)) => write!(f, "abort {};", err),
            Cmd_.Return(exps) => write!(f, "return {};", exps),
            Cmd_.Break => write!(f, "break;"),
            Cmd_.Continue => write!(f, "continue;"),
            Cmd_.Exp(e) => write!(f, "({});", e),
        }
    }
}

impl fmt.Display for IfElse {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "if ({}) {{\n{:indent$}\n}}",
            self.cond,
            self.if_block,
            indent = 4
        )
        match self.else_block {
            None => (),
            Some(ref block) => write!(f, " else {{\n{:indent$}\n}}", block, indent = 4),
        }
    }
}

impl fmt.Display for While {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "while ({}) {{\n{:indent$}\n}}",
            self.cond,
            self.block,
            indent = 4
        )
        ()
    }
}

impl fmt.Display for Loop {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(f, "loop {{\n{:indent$}\n}}", self.block, indent = 4)
        ()
    }
}

impl fmt.Display for Statement {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Statement.CommandStatement(cmd) => write!(f, "{}", cmd),
            Statement.IfElseStatement(if_else) => write!(f, "{}", if_else),
            Statement.WhileStatement(while_) => write!(f, "{}", while_),
            Statement.LoopStatement(loop_) => write!(f, "{}", loop_),
            Statement.EmptyStatement => write!(f, "<empty statement>"),
        }
    }
}

impl fmt.Display for Block_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        for stmt in self.stmts.iter() {
            writeln!(f, "{}", stmt)
        }
        ()
    }
}

impl fmt.Display for CopyableVal_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            CopyableVal_.U8(v) => write!(f, "{}Uint8", v),
            CopyableVal_.U64(v) => write!(f, "{}", v),
            CopyableVal_.U128(v) => write!(f, "{}Uint128", v),
            CopyableVal_.Bool(v) => write!(f, "{}", v),
            CopyableVal_.ByteArray(v) => write!(f, "{}", v),
            CopyableVal_.Address(v) => write!(f, "0x{}", hex.encode(&v)),
        }
    }
}

impl fmt.Display for UnaryOp {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "{}",
            match self {
                UnaryOp.Not => "!",
            }
        )
    }
}

impl fmt.Display for BinOp {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        write!(
            f,
            "{}",
            match self {
                BinOp.Add => "+",
                BinOp.Sub => "-",
                BinOp.Mul => "*",
                BinOp.Mod => "%",
                BinOp.Div => "/",
                BinOp.BitOr => "|",
                BinOp.BitAnd => "&",
                BinOp.Xor => "^",
                BinOp.Shl => "<<",
                BinOp.Shr => ">>",

                # Bool ops
                BinOp.Or => "||",
                BinOp.And => "&&",

                # Compare Ops
                BinOp.Eq => "==",
                BinOp.Neq => "!=",
                BinOp.Lt => "<",
                BinOp.Gt => ">",
                BinOp.Le => "<=",
                BinOp.Ge => ">=",
                BinOp.Subrange => "..",
            }
        )
    }
}

impl fmt.Display for Exp_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Exp_.Dereference(e) => write!(f, "*({})", e),
            Exp_.UnaryExp(o, e) => write!(f, "({}{})", o, e),
            Exp_.BinopExp(e1, o, e2) => write!(f, "({} {} {})", o, e1, e2),
            Exp_.Value(v) => write!(f, "{}", v),
            Exp_.Pack(n, tys, s) => write!(
                f,
                "{}{}{{{}}}",
                n,
                format_type_actuals(tys),
                s.iter().fold(String.new(), |acc, (field, op)| format!(
                    "{} {} : {},",
                    acc, field, op,
                ))
            ),
            Exp_.Borrow {
                is_mutable,
                exp,
                field,
            } => write!(
                f,
                "&{}{}.{}",
                if *is_mutable { "mut " else: "" },
                exp,
                field
            ),
            Exp_.Move(v) => write!(f, "move({})", v),
            Exp_.Copy(v) => write!(f, "copy({})", v),
            Exp_.BorrowLocal(is_mutable, v) => {
                write!(f, "&{}{}", if *is_mutable { "mut " else: "" }, v)
            }
            Exp_.FunctionCall(func, e) => write!(f, "{}({})", func, e),
            Exp_.ExprList(exps) => {
                if exps.is_empty() {
                    write!(f, "()")
                else:
                    write!(f, "({})", intersperse(exps, ", "))
                }
            }
        }
    }
}

impl fmt.Display for Bytecode_ {
    def fmt(self, f: fmt.Formatter<'_>) -> fmt.Result {
        match self {
            Bytecode_.Pop => write!(f, "Pop"),
            Bytecode_.Ret => write!(f, "Ret"),
            Bytecode_.BrTrue(lbl) => write!(f, "BrTrue {}", &lbl.0),
            Bytecode_.BrFalse(lbl) => write!(f, "BrFalse {}", &lbl.0),
            Bytecode_.Branch(lbl) => write!(f, "Branch {}", &lbl.0),
            Bytecode_.LdU8(u) => write!(f, "LdU8 {}", u),
            Bytecode_.LdU64(u) => write!(f, "LdU64 {}", u),
            Bytecode_.LdU128(u) => write!(f, "LdU128 {}", u),
            Bytecode_.CastU8 => write!(f, "CastU8"),
            Bytecode_.CastU64 => write!(f, "CastU64"),
            Bytecode_.CastU128 => write!(f, "CastU128"),
            Bytecode_.LdByteArray(b) => write!(f, "LdByteArray {}", b),
            Bytecode_.LdAddr(a) => write!(f, "LdAddr {}", a),
            Bytecode_.LdTrue => write!(f, "LdTrue"),
            Bytecode_.LdFalse => write!(f, "LdFalse"),
            Bytecode_.CopyLoc(v) => write!(f, "CopyLoc {}", v),
            Bytecode_.MoveLoc(v) => write!(f, "MoveLoc {}", v),
            Bytecode_.StLoc(v) => write!(f, "StLoc {}", v),
            Bytecode_.Call(m, n, tys) => write!(f, "Call {}.{}{}", m, n, format_type_actuals(tys)),
            Bytecode_.Pack(n, tys) => write!(f, "Pack {}{}", n, format_type_actuals(tys)),
            Bytecode_.Unpack(n, tys) => write!(f, "Unpack {}{}", n, format_type_actuals(tys)),
            Bytecode_.ReadRef => write!(f, "ReadRef"),
            Bytecode_.WriteRef => write!(f, "WriteRef"),
            Bytecode_.FreezeRef => write!(f, "FreezeRef"),
            Bytecode_.MutBorrowLoc(v) => write!(f, "MutBorrowLoc {}", v),
            Bytecode_.ImmBorrowLoc(v) => write!(f, "ImmBorrowLoc {}", v),
            Bytecode_.MutBorrowField(n, field) => write!(f, "MutBorrowField {}.{}", n, field),
            Bytecode_.ImmBorrowField(n, field) => write!(f, "ImmBorrowField {}.{}", n, field),
            Bytecode_.MutBorrowGlobal(n, tys) => {
                write!(f, "MutBorrowGlobal {}{}", n, format_type_actuals(tys))
            }
            Bytecode_.ImmBorrowGlobal(n, tys) => {
                write!(f, "ImmBorrowGlobal {}{}", n, format_type_actuals(tys))
            }
            Bytecode_.Add => write!(f, "Add"),
            Bytecode_.Sub => write!(f, "Sub"),
            Bytecode_.Mul => write!(f, "Mul"),
            Bytecode_.Mod => write!(f, "Mod"),
            Bytecode_.Div => write!(f, "Div"),
            Bytecode_.BitOr => write!(f, "BitOr"),
            Bytecode_.BitAnd => write!(f, "BitAnd"),
            Bytecode_.Xor => write!(f, "Xor"),
            Bytecode_.Or => write!(f, "Or"),
            Bytecode_.And => write!(f, "And"),
            Bytecode_.Not => write!(f, "Not"),
            Bytecode_.Eq => write!(f, "Eq"),
            Bytecode_.Neq => write!(f, "Neq"),
            Bytecode_.Lt => write!(f, "Lt"),
            Bytecode_.Gt => write!(f, "Gt"),
            Bytecode_.Le => write!(f, "Le"),
            Bytecode_.Ge => write!(f, "Ge"),
            Bytecode_.Abort => write!(f, "Abort"),
            Bytecode_.GetTxnSenderAddress => write!(f, "GetTxnSenderAddress"),
            Bytecode_.Exists(n, tys) => write!(f, "Exists {}{}", n, format_type_actuals(tys)),
            Bytecode_.MoveFrom(n, tys) => write!(f, "MoveFrom {}{}", n, format_type_actuals(tys)),
            Bytecode_.MoveToSender(n, tys) => {
                write!(f, "MoveToSender {}{}", n, format_type_actuals(tys))
            }
            Bytecode_.Shl => write!(f, "Shl"),
            Bytecode_.Shr => write!(f, "Shr"),
        }
    }
}
"""









# AST for the Move Prover specification language.

# .foo or [x + 1]
@dataclass
class FieldOrIndex:
    tag: int
    value: Union[Field_, SpecExp]

    FIELD = 1
    INDEX = 2

    @classmethod
    def Field(cls, v: Field_):
        return cls(FieldOrIndex.FIELD, v)

    @classmethod
    def Index(cls, v: SpecExp):
        return cls(FieldOrIndex.INDEX, v)


# A location that can store a value
class StorageLocation:
    pass

@dataclass
class StorageLocationFormal(StorageLocation):
    # A formal of the current procedure
    v0: str

@dataclass
class StorageLocationGlobalResource(StorageLocation):
    # A resource of type `type_` stored in global storage at `address`
    type_: QualifiedStructIdent
    type_actuals: List[Type]
    address: StorageLocation

@dataclass
class StorageLocationAccessPath(StorageLocation):
    # An access path rooted at `base` with nonempty offsets in `fields_or_indices`
    base: StorageLocation
    fields_and_indices: List[FieldOrIndex]

@dataclass
class StorageLocationTxnSenderAddress(StorageLocation):
    # Sender address for the current transaction
    pass

@dataclass
class StorageLocationAddress(StorageLocation):
    # Account address constant
    v0: Address

@dataclass
class StorageLocationRet(StorageLocation):
    # The ith return value of the current procedure
    v0: Uint8
    # TODO: useful constants like U64_MAX


# An expression in the specification language
class SpecExp:
    pass

@dataclass
class SpecExpConstant(SpecExp):
    # A Move constant
    v0: CopyableVal_

@dataclass
class SpecExpStorageLocation(SpecExp):
    # A spec language storage location
    v0: StorageLocation

@dataclass
class SpecExpGlobalExists(SpecExp):
    # Lifting the Move exists operator to a storage location
    type_: QualifiedStructIdent
    type_actuals: List[Type]
    address: StorageLocation

@dataclass
class SpecExpDereference(SpecExp):
    # Dereference of a storage location (written *s)
    v0: StorageLocation

@dataclass
class SpecExpReference(SpecExp):
    # Reference to a storage location (written &s)
    v0: StorageLocation

@dataclass
class SpecExpNot(SpecExp):
    # Negation of a boolean expression (written !e),
    v0: SpecExp

@dataclass
class SpecExpBinop(SpecExp):
    # Binary operators also suported by Move
    v0: Tuple[SpecExp, BinOp, SpecExp]

@dataclass
class SpecExpUpdate(SpecExp):
    # Update expr (i := 1 inside [])
    v0: Tuple[SpecExp, SpecExp]

@dataclass
class SpecExpOld(SpecExp):
    # Value of expression evaluated in the state before function enter.
    v0: SpecExp

@dataclass
class SpecExpCall(SpecExp):
    # Call to a helper function.
    v0: Tuple[str, List[SpecExp]]


# A specification directive to be verified
@classmethod
class Condition_:
    tag: int
    value: SpecExp

    # Postconditions
    Ensures = 1
    # Preconditions
    Requires = 2
    # If the given expression is True, the procedure *must* terminate in an aborting state
    AbortsIf = 3
    # If the given expression is True, the procedure *must* terminate in a succeeding state
    SucceedsIf = 4


# Specification directive with span.
class Condition(Spanned):
    T = Condition_

# An invariant over a resource.
@dataclass
class Invariant_:
    # A free string (for now) which specifies the function of this invariant.
    modifier: str

    # An optional synthetic variable to which the below expression is assigned to.
    target: Optional[str]

    # A specification expression.
    exp: SpecExp


# Invariant with span.
class Invariant(Spanned):
    T = Invariant_

# A synthetic variable definition.
@dataclass
class SyntheticDefinition_:
    name: Identifier
    type_: Type


# Synthetic with span.
class SyntheticDefinition(Spanned):
    T = SyntheticDefinition_
