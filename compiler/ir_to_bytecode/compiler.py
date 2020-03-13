from __future__ import annotations
from compiler.ir_to_bytecode.context import Context, MaterializedPools
from compiler.ir_to_bytecode.errors import *
from compiler.bytecode_source_map.source_map import ModuleSourceMap
from libra.account_address import Address
from move_ir.types import ast
from move_ir.types.ast import *
from move_ir.types.ast import Bytecode as IRBytecode
from move_ir.types.ast import Bytecode_ as IRBytecode_
from move_ir.types.location import *
from libra_vm.file_format import (
        self_module_name, Bytecode, CodeOffset, CodeUnit, CompiledModule, CompiledModuleMut, CompiledProgram,
        CompiledScript, CompiledScriptMut, FieldDefinition, FieldDefinitionIndex,
        FunctionDefinition, FunctionSignature, Kind, LocalsSignature, MemberCount, SignatureToken,
        StructDefinition, StructFieldInformation, StructHandleIndex, TableIndex, ModuleAccess
    )
from libra_vm import signature_token_help
from typing import List, Optional, Tuple, Mapping
from dataclasses import dataclass
from libra.rustlib import bail, ensure, usize
from canoser import Uint8, Uint16, Uint64, Int64
from itertools import chain
from enum import IntEnum
from copy import deepcopy

def record_src_loc_local(context, var):
    source_name = (var.value, var.loc)
    context.source_map\
        .add_local_mapping(context.current_function_definition_index(), source_name)

def record_src_loc_field(context, field):
    context.source_map\
        .add_struct_field_mapping(context.current_struct_definition_index(), field.loc)

def record_src_loc_function_type_formals(context, var):
    for (ty_var, _) in var:
        source_name = (ty_var.value, ty_var.loc)
        context.source_map.add_function_type_parameter_mapping(
            context.current_function_definition_index(),
            source_name,
        )

def record_src_loc_function_decl(context, location, function_index):
    context.set_function_index(function_index)
    context.source_map.add_top_level_function_mapping(
        context.current_function_definition_index(),
        location,
    )

def record_src_loc_struct_type_formals(context, var):
    for (ty_var, _) in var:
        source_name = (ty_var.value.clone().into_inner(), ty_var.loc)
        context.source_map.add_struct_type_parameter_mapping(
            context.current_struct_definition_index(),
            source_name,
        )

def record_src_loc_struct_decl(context, location):
    context.source_map\
        .add_top_level_struct_mapping(context.current_struct_definition_index(), location)

def make_push_instr(context, code):
    def push_instr(loc, instr):
        code_offset = code.__len__()
        context.source_map.add_code_mapping(
            context.current_function_definition_index(),
            code_offset,
            loc,
        )
        code.append(instr)
    return push_instr



@dataclass
class LoopInfo:
    start_loc: usize
    breaks: List[usize]


# Ideally, we should capture all of this info into a CFG, but as we only have structured control
# flow currently, it would be a bit overkill. It will be a necessity if we add arbitrary branches
# in the IR, as is expressible in the bytecode
@dataclass
class  ControlFlowInfo:
    # A `break` is reachable iff it was used before a terminal node
    reachable_break: bool
    # A terminal node is an infinite loop or a path that always returns
    terminal_node: bool

    @staticmethod
    def join(f1: ControlFlowInfo, f2: ControlFlowInfo) -> ControlFlowInfo:
        return ControlFlowInfo(
            f1.reachable_break or f2.reachable_break,
            f1.terminal_node and f2.terminal_node,
        )

    @staticmethod
    def successor(prev: ControlFlowInfo, nextt: ControlFlowInfo) -> ControlFlowInfo:
        if prev.terminal_node:
            return prev
        else:
            return ControlFlowInfo(
                prev.reachable_break or nextt.reachable_break,
                nextt.terminal_node,
            )


# Inferred representation of SignatureToken's
# In essence, it's a signature token with a "bottom" type added
class InferredTypeTag(IntEnum):
    # Result of the compiler failing to infer the type of an expression
    # Not translatable to a signature token
    Anything = 0

    # Signature tokens
    Bool = SerializedType.BOOL
    U8 = SerializedType.U8
    U64 = SerializedType.U64
    U128 = SerializedType.U128
    ByteArray = SerializedType.BYTEARRAY
    Address = SerializedType.ADDRESS
    Vector = SerializedType.VECTOR
    Struct = SerializedType.STRUCT
    Reference = SerializedType.REFERENCE
    MutableReference = SerializedType.MUTABLE_REFERENCE
    TypeParameter = SerializedType.TYPE_PARAMETER

@dataclass
class InferredType:
    tag: InferredTypeTag
    struct : StructHandleIndex = None
    reference : InferredType = None
    typeParameter : str = None
    vector_type: InferredType = None

    @classmethod
    def Vector(cls, v):
        return cls(InferredTypeTag.Vector, vector_type=v)

    @classmethod
    def Struct(cls, v):
        return cls(InferredTypeTag.Struct, struct=v)

    @classmethod
    def Reference(cls, v):
        return cls(InferredTypeTag.Reference, reference=v)

    @classmethod
    def MutableReference(cls, v):
        return cls(InferredTypeTag.MutableReference, reference=v)

    @classmethod
    def TypeParameter(cls, v):
        return cls(InferredTypeTag.typeParameter, typeParameter=v)

    @classmethod
    def from_signature_token(cls, sig_token: SignatureToken) -> InferredType:
        if sig_token.is_primitive():
            return InferredType(sig_token.tag)

        elif sig_token.tag == SerializedType.VECTOR:
            return cls.Vector(cls.from_signature_token(sig_token.vector_type))

        elif sig_token.tag == SerializedType.STRUCT:
            (si, _) = sig_token.struct
            return cls.Struct(si)

        elif sig_token.tag == SerializedType.REFERENCE:
            return cls.Reference(cls.from_signature_token(sig_token.reference))

        elif sig_token.tag == SerializedType.MUTABLE_REFERENCE:
            return cls.MutableReference(cls.from_signature_token(sig_token.reference))

        elif sig_token.tag == SerializedType.TYPE_PARAMETER:
            return cls.TypeParameter(sig_token.typeParameter.__str__())
        else:
            bail("unreachable!")


    def get_struct_handle(self) -> StructHandleIndex:
        if self.tag == InferredTypeTag.Reference or self.tag == InferredTypeTag.MutableReference:
            return self.reference.get_struct_handle()
        elif self.tag == InferredTypeTag.Struct:
            return self.struct
        else:
            bail("could not infer class type")

InferredType.Bool = InferredType(InferredTypeTag.Bool)
InferredType.U8 = InferredType(InferredTypeTag.U8)
InferredType.U64 = InferredType(InferredTypeTag.U64)
InferredType.U128 = InferredType(InferredTypeTag.U128)
InferredType.Address = InferredType(InferredTypeTag.Address)
InferredType.ByteArray = InferredType(InferredTypeTag.ByteArray)
InferredType.Anything = InferredType(InferredTypeTag.Anything)


# Holds information about a function being compiled.
@dataclass
class FunctionFrame:
    local_count: Uint8
    locls: Mapping[Var_, Uint8]
    local_types: LocalsSignature
    # Int64 to allow the bytecode verifier to catch errors of
    # - negative stack sizes
    # - excessivley large stack sizes
    # The max stack depth of the file_format is set.
    # Theoretically, we could use a BigInt here, but that is probably overkill for any testing
    max_stack_depth: Int64
    cur_stack_depth: Int64
    loops: List[LoopInfo]

    @classmethod
    def new(cls) -> FunctionFrame:
        return cls(0, {}, LocalsSignature(), 0, 0, [])


    # Manage the stack info for the function
    def push(self) -> None:
        if self.cur_stack_depth == Int64.max_value:
            bail("ICE Stack depth accounting overflow. The compiler can only support a maximum stack depth of up to Int64.max_value")

        self.cur_stack_depth += 1
        self.max_stack_depth = max(self.max_stack_depth, self.cur_stack_depth)


    def pop(self) -> None:
        if self.cur_stack_depth == Int64.min_value:
            bail("ICE Stack depth accounting underflow. The compiler can only support a minimum stack depth of up to Int64.min_value")

        self.cur_stack_depth -= 1


    def get_local(self, var: Var_) -> Uint8:
        idx = self.locls.get(var)
        if idx is None:
            bail("variable {} undefined", var)
        else:
            return idx



    def get_local_type(self, idx: Uint8) -> SignatureToken:
        try:
            return self.local_types.v0[idx]
        except:
            bail("variable {} undefined", idx)


    def define_local(self, var: Var_, type_: SignatureToken) -> Uint8:
        if self.local_count >= Uint8.max_value:
            bail("Max number of locals reached")

        cur_loc_idx = self.local_count
        if var in self.locls:
            bail("variable redefinition {}", var)
        else:
            self.locls[var] = cur_loc_idx
            self.local_types.v0.append(type_)
            self.local_count += 1
            return cur_loc_idx


    def push_loop(self, start_loc: usize) -> None:
        self.loops.append(LoopInfo(start_loc, []))


    def pop_loop(self) -> None:
        loop = self.loops.pop()


    def get_loop_start(self) -> usize:
        if self.loops:
            return self.loops[-1].start_loc
        else:
            bail("continue outside loop")


    def push_loop_break(self, loc: usize) -> None:
        if self.loops:
            return self.loops[-1].breaks.append(loc)
        else:
            bail("break outside loop")


    def get_loop_breaks(self) -> List[usize]:
        if self.loops:
            return self.loops[-1].breaks
        else:
            bail("Impossible: failed to get loop breaks (no loops in stack)")


# Compile a transaction program.
def compile_program(
    address: Address,
    program: Program,
    deps: List[ModuleAccess],
) -> Tuple[CompiledProgram, SourceMap]:
    deps = [dep.as_module() for dep in deps]

    # This is separate to avoid unnecessary code gen due to monomorphization.
    modules = []
    source_maps = []
    for m in program.modules:
        deps2 = chain(deps, modules)
        (module, source_map) = compile_module(address, m, deps2)
        deps2 = None
        modules.append(module)
        source_maps.append(source_map)


    deps = chain(deps, modules)
    (script, source_map) = compile_script(address, program.script, deps)
    source_maps.append(source_map)
    return (CompiledProgram(modules, script), source_maps)


# Compile a transaction script.
def compile_script(
    address: Address,
    script: Script,
    dependencies: List[ModuleAccess],
) -> Tuple[CompiledScript, ModuleSourceMap]:
    current_module = QualifiedModuleIdent(
        address = address,
        name = self_module_name(),
    )

    context = Context.new(dependencies, current_module)
    self_name = SELF_MODULE_NAME

    compile_imports(context, address, script.imports)
    compile_explicit_dependency_declarations(
        context,
        script.explicit_dependency_declarations,
    )
    main_name = "main"
    function = script.main

    sig = function_signature(context, function.value.signature)
    context.declare_function(self_name, main_name, sig)
    main = compile_function(context, self_name, main_name, function, 0)


    mpools, source_map = context.materialize_pools()
    compiled_script = CompiledScriptMut(
        mpools.module_handles,
        mpools.struct_handles,
        mpools.function_handles,
        mpools.type_signatures,
        mpools.function_signatures,
        mpools.locals_signatures,
        mpools.identifiers,
        mpools.byte_array_pool,
        mpools.address_pool,
        main,
    )
    return (compiled_script.freeze(), source_map)
        # .map_err(|errs| InternalCompilerError.BoundsCheckErrors(errs).into())


# Compile a module.
def compile_module(
    address: Address,
    module: ModuleDefinition,
    dependencies: List[ModuleAccess],
) -> Tuple[CompiledModule, ModuleSourceMap]:
    current_module = QualifiedModuleIdent(
        address = address,
        name = module.name,
    )
    context = Context.new(dependencies, current_module)
    self_name = SELF_MODULE_NAME
    # Explicitly declare all imports as they will be included even if not used
    compile_imports(context, address, module.imports)

    # Explicitly declare all structs as they will be included even if not used
    for s in module.structs:
        ident = QualifiedStructIdent(
            module= self_name,
            name= s.value.name,
        )
        (_, tys) = type_formals(s.value.type_formals)
        context.declare_struct_handle_index(ident, s.value.is_nominal_resource, tys)


    # Add explicit handles/dependency declarations to the pools
    compile_explicit_dependency_declarations(
        context,
        module.explicit_dependency_declarations,
    )

    for (name, function) in module.functions:
        sig = function_signature(context, function.value.signature)
        context.declare_function(self_name, name, sig)

    # Current module
    (struct_defs, field_defs) = compile_structs(context, self_name, module.structs)

    function_defs = compile_functions(context, self_name, module.functions)

    mpools, source_map = context.materialize_pools()
    compiled_module = CompiledModuleMut(
        mpools.module_handles,
        mpools.struct_handles,
        mpools.function_handles,
        mpools.type_signatures,
        mpools.function_signatures,
        mpools.locals_signatures,
        mpools.identifiers,
        mpools.byte_array_pool,
        mpools.address_pool,
        struct_defs,
        field_defs,
        function_defs,
    )
    return (compiled_module.freeze(), source_map)


def compile_explicit_dependency_declarations(
    context: Context,
    dependencies: List[ModuleDependency],
) -> None:
    for dependency in dependencies:
        for struct_dep in structs:
            sname = QualifiedStructIdent(dependency.name, struct_dep.name)
            (_, kinds) = type_formals(struct_dep.type_formals)
            context.declare_struct_handle_index(sname, struct_dep.is_nominal_resource, kinds)

        for function_dep in functions:
            sig = function_signature(context, function_dep.signature)
            context.declare_function(dependency.name, function_dep.name, sig)


def compile_imports(
    context: Context,
    address: Address,
    imports: List[ImportDefinition],
) -> None:
    for imp in imports:
        if imp.tag == ModuleIdent.TRANSACTION:
            ident = QualifiedModuleIdent(imp.value, address)
        elif imp.tag == ModuleIdent.QUALIFIED:
            ident = imp.value
        else:
            bail("unreachable!")
        context.declare_import(ident, imp.alias)



def type_formals(
    ast_tys: List[Tuple[TypeVar, ast.Kind]]
) -> Tuple[Mapping[TypeVar_, usize], List[Kind]]:
    m = {}
    tys = []
    for (idx, (ty_var, k)) in enumerate(ast_tys):
        if ty_var.value in m:
            bail("Type formal '{}'' already bound", ty_var)
        else:
            m[ty_var.value] = idx
        tys.append(kind(k))

    return (m, tys)


def kind(ast_k: ast.Kind) -> Kind:
    return Kind(ast_k)


def compile_types(context: Context, tys: List[Type]) -> List[SignatureToken]:
    return [compile_type(context, ty) for ty in tys]


def compile_type(context: Context, ty: Type) -> SignatureToken:
    if ty.tag.is_primitive():
        return SignatureToken(ty.tag)

    elif ty.tag == SerializedType.VECTOR:
        return signature_token_help.Vector(compile_type(context, ty.vector))

    elif ty.tag == SerializedType.REFERENCE:
        (is_mutable, inner_type) = ty.reference
        inner_token = compile_type(context, inner_type)
        if is_mutable:
            return signature_token_help.MutableReference(inner_token)
        else:
            return signature_token_help.Reference(inner_token)

    elif ty.tag == SerializedType.STRUCT:
        (ident, tys) = ty.struct
        sh_idx = context.struct_handle_index(ident)
        tokens = compile_types(context, tys)
        return signature_token_help.Struct(sh_idx, tokens)

    elif ty.tag == SerializedType.TYPE_PARAMETER:
        return signature_token_help.TypeParameter(context.type_formal_index(ty.typeParameter))
    else:
        bail("unreachable!")



def function_signature(
    context: Context,
    f: ast.FunctionSignature,
) -> FunctionSignature:
    (amap, _) = type_formals(f.type_formals)
    context.bind_type_formals(amap)
    return_types = compile_types(context, f.return_type)
    arg_types = [compile_type(context, ty) for (_, ty) in f.formals]
    typeformals = [kind(k) for (_, k) in f.type_formals]
    return FunctionSignature(
        return_types,
        arg_types,
        typeformals,
    )

def compile_structs(
    context: Context,
    self_name: ModuleName,
    structs: List[ast.StructDefinition],
) -> Tuple[List[StructDefinition], List[FieldDefinition]]:
    struct_defs = []
    field_defs = []
    for s in structs:
        sident = QualifiedStructIdent(
            module= self_name,
            name= s.value.name,
        )
        sh_idx = context.struct_handle_index(sident)
        record_src_loc_struct_decl(context, s.loc)
        record_src_loc_struct_type_formals(context, s.value.type_formals)
        (amap, _) = type_formals(s.value.type_formals)
        context.bind_type_formals(amap)
        field_information = compile_fields(context, field_defs, sh_idx, s.value.fields)
        context.declare_struct_definition_index(s.value.name)
        struct_defs.append(StructDefinition(
            sh_idx,
            field_information,
        ))

    return (struct_defs, field_defs)


def compile_fields(
    context: Context,
    field_pool: List[FieldDefinition],
    sh_idx: StructHandleIndex,
    sfields: StructDefinitionFields,
) -> StructFieldInformation:
    if sfields.tag == StructDefinitionFields.NATIVE:
        return StructFieldInformation.Native()
    else:
        fields = sfields.fields
        pool_len = field_pool.__len__()
        field_count = fields.__len__()

        field_information = StructFieldInformation.Declared(
            field_count= (field_count),
            fields= FieldDefinitionIndex(pool_len),
        )

        for (decl_order, (f, ty)) in enumerate(fields):
            name = context.identifier_index(f.value)
            record_src_loc_field(context, f)
            sig_token = compile_type(context, ty)
            signature = context.type_signature_index(deepcopy(sig_token))
            context.declare_field(sh_idx, f.value, sig_token, decl_order)
            field_pool.append(FieldDefinition(
                sh_idx,
                name,
                signature,
            ))

        return field_information



def compile_functions(
    context: Context,
    self_name: ModuleName,
    functions: List[Tuple[FunctionName, Function]],
) -> List[FunctionDefinition]:
    return [compile_function(context, self_name, name, ast_function, func_index) \
        for (func_index, (name, ast_function)) in enumerate(functions)]


def compile_function(
    context: Context,
    self_name: ModuleName,
    name: FunctionName,
    ast_function: Function,
    function_index: usize,
) -> FunctionDefinition:
    record_src_loc_function_decl(context, ast_function.loc, function_index)
    record_src_loc_struct_type_formals(context,
        ast_function.value.signature.type_formals
    )
    fh_idx = context.function_handle(self_name, name)[1]

    ast_function = ast_function.value

    if isinstance(ast_function.body, FunctionBodyNative):
        flags = ast_function.visibility | CodeUnit.NATIVE
    else:
        flags = ast_function.visibility

    acquires_global_resources = [context.struct_definition_index(name) \
        for name in ast_function.acquires]

    if isinstance(ast_function.body, FunctionBodyMove):
        (m, _) = type_formals(ast_function.signature.type_formals)
        context.bind_type_formals(m)
        code = compile_function_body(
            context, ast_function.signature.formals,
            ast_function.body.locls, ast_function.body.code,
        )
    elif isinstance(ast_function.body, FunctionBodyBytecode):
        (m, _) = type_formals(ast_function.signature.type_formals)
        context.bind_type_formals(m)
        code = compile_function_body_bytecode(
            context, ast_function.signature.formals,
            ast_function.body.locls, ast_function.body.code,
        )
    elif isinstance(ast_function.body, FunctionBodyNative):
        for (var, _) in ast_function.signature.formals:
            record_src_loc_local(context, var)
        code = CodeUnit()
    else:
        bail("unreachable!")

    return FunctionDefinition(
        fh_idx,
        flags,
        acquires_global_resources,
        code,
    )

def compile_function_body(
    context: Context,
    formals: List[Tuple[Var, Type]],
    locls: List[Tuple[Var, Type]],
    block: Block_,
) -> CodeUnit:
    function_frame = FunctionFrame.new()
    locals_signature = LocalsSignature([])
    for (var, t) in formals:
        sig = compile_type(context, t)
        function_frame.define_local(var.value, deepcopy(sig))
        locals_signature.v0.append(sig)
        record_src_loc_local(context, var)

    for (var_, t) in locls:
        sig = compile_type(context, t)
        function_frame.define_local(var_.value, deepcopy(sig))
        locals_signature.v0.append(sig)
        record_src_loc_local(context, var_)

    sig_idx = context.locals_signature_index(locals_signature)

    code = []
    compile_block(context, function_frame, code, block)

    if function_frame.max_stack_depth < 0:
        max_stack_size = 0
    elif function_frame.max_stack_depth > Uint16.max_value:
        max_stack_size = Uint16.max_value
    else:
        max_stack_size = function_frame.max_stack_depth

    return CodeUnit(
        max_stack_size,
        sig_idx,
        code,
    )


def compile_block(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    block: Block_,
) -> ControlFlowInfo:
    cf_info = ControlFlowInfo(
        reachable_break= False,
        terminal_node= False,
    )
    for stmt in block.stmts:
        if isinstance(stmt, CommandStatement):
            stmt_info = compile_command(context, function_frame, code, stmt.v0)

        elif isinstance(stmt, WhileStatement):
            stmt_info = compile_while(context, function_frame, code, stmt.v0)

        elif isinstance(stmt, LoopStatement):
            stmt_info = compile_loop(context, function_frame, code, stmt.v0)

        elif isinstance(stmt, IfElseStatement):
            stmt_info = compile_if_else(context, function_frame, code, stmt.v0)

        elif isinstance(stmt, EmptyStatement):
            continue
        else:
            bail("unreachable!")

        cf_info = ControlFlowInfo.successor(cf_info, stmt_info)
    return cf_info


def compile_if_else(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    if_else: IfElse,
) -> ControlFlowInfo:
    push_instr = make_push_instr(context, code)
    cond_span = if_else.cond.loc
    compile_expression(context, function_frame, code, if_else.cond)

    brFalse_ins_loc = code.__len__()
    # placeholder, final branch target replaced later
    push_instr(cond_span, Bytecode(Opcodes.BR_FALSE, 0))
    function_frame.pop()
    if_cf_info = compile_block(context, function_frame, code, if_else.if_block.value)

    else_block_location = code.__len__()

    if if_else.else_block is None:
        else_cf_info =  ControlFlowInfo(
            reachable_break= False,
            terminal_node= False,
        )
    else:
        else_block = if_else.else_block
        branch_ins_loc = code.__len__()
        if not if_cf_info.terminal_node:
            # placeholder, final branch target replaced later
            push_instr(else_block.loc, Bytecode(Opcodes.BRANCH, 0))
            else_block_location += 1

        else_cf_info = compile_block(context, function_frame, code, else_block.value)
        if not if_cf_info.terminal_node:
            code[branch_ins_loc] = Bytecode(Opcodes.BRANCH, code.__len__())

    code[brFalse_ins_loc] = Bytecode(Opcodes.BR_FALSE, else_block_location)
    return ControlFlowInfo.join(if_cf_info, else_cf_info)


def compile_while(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    while_: While,
) -> ControlFlowInfo:
    push_instr = make_push_instr(context, code)
    cond_span = while_.cond.loc
    loop_start_loc = code.__len__()
    function_frame.push_loop(loop_start_loc)
    compile_expression(context, function_frame, code, while_.cond)

    brFalse_loc = code.__len__()

    # placeholder, final branch target replaced later
    push_instr(cond_span, Bytecode(Opcodes.BR_FALSE, 0))
    function_frame.pop()

    compile_block(context, function_frame, code, while_.block.value)
    push_instr(while_.block.loc, Bytecode(Opcodes.BRANCH, loop_start_loc))

    loop_end_loc = code.__len__()
    code[brFalse_loc] = Bytecode(Opcodes.BR_FALSE, loop_end_loc)
    breaks = function_frame.get_loop_breaks()
    for i in breaks:
        code[i] = Bytecode(Opcodes.BRANCH, loop_end_loc)


    function_frame.pop_loop()
    return ControlFlowInfo(
        # this `reachable_break` break is for any outer loop
        # not the loop that was just compiled
        reachable_break= False,
        # While always has the ability to break.
        # Conceptually we treat
        #   `while (cond { body }`
        # as `
        #   `loop { if (cond) { body; continue; else: break; } }`
        # So a `break` is always reachable
        terminal_node= False,
    )


def compile_loop(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    loop_: Loop,
) -> ControlFlowInfo:
    push_instr = make_push_instr(context, code)
    loop_start_loc = code.__len__()
    function_frame.push_loop(loop_start_loc)

    body_cf_info = compile_block(context, function_frame, code, loop_.block.value)
    push_instr(loop_.block.loc, Bytecode(Opcodes.BRANCH, loop_start_loc))

    loop_end_loc = code.__len__()
    breaks = function_frame.get_loop_breaks()
    for i in breaks:
        code[i] = Bytecode(Opcodes.BRANCH, loop_end_loc)


    function_frame.pop_loop()
    # this `reachable_break` break is for any outer loop
    # not the loop that was just compiled
    reachable_break = False
    # If the body of the loop does not have a break, it will loop forever
    # and thus is a terminal node
    terminal_node = not body_cf_info.reachable_break
    return ControlFlowInfo(
        reachable_break,
        terminal_node,
    )


def compile_command(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    cmd: Cmd,
) -> ControlFlowInfo:
    push_instr = make_push_instr(context, code)
    if cmd.value.tag in [
        CmdTag.Continue,
        CmdTag.Abort,
        CmdTag.Return,
    ]:
        # If we are in a loop, `continue` makes a terminal node
        # Conceptually we treat
        #   `while (cond) { body }`
        # as `
        #   `loop { if (cond) { body; continue; else: break; } }`
        # `return` and `abort` alway makes a terminal node
        (reachable_break, terminal_node) = (False, True)
    elif cmd.value.tag == CmdTag.Break:
        (reachable_break, terminal_node) = (True, False)
    else:
        (reachable_break, terminal_node) = (False, False)


    if cmd.value.tag == CmdTag.Return:
        compile_expression(context, function_frame, code, cmd.value.value)
        push_instr(cmd.loc, Bytecode(Opcodes.RET))

    elif cmd.value.tag == CmdTag.Abort:
        exp_opt = cmd.value.value
        if exp_opt is not None:
            compile_expression(context, function_frame, code, exp_opt)

        push_instr(cmd.loc, Bytecode(Opcodes.ABORT))
        function_frame.pop()

    elif cmd.value.tag == CmdTag.Assign:
        (lvalues, rhs_expressions) = cmd.value.value
        compile_expression(context, function_frame, code, rhs_expressions)
        compile_lvalues(context, function_frame, code, lvalues)

    elif cmd.value.tag == CmdTag.Unpack:
        (name, tys, bindings, e) = cmd.value.value
        tokens = LocalsSignature(compile_types(context, tys))
        type_actuals_id = context.locals_signature_index(tokens)

        compile_expression(context, function_frame, code, e)

        def_idx = context.struct_definition_index(name)
        push_instr(cmd.loc, Bytecode(Opcodes.UNPACK, (def_idx, type_actuals_id)))
        function_frame.pop()

        for (field_, lhs_variable) in reversed(bindings):
            loc_idx = function_frame.get_local(lhs_variable.value)
            st_loc = Bytecode(Opcodes.ST_LOC, loc_idx)
            push_instr(field_.loc, st_loc)

    elif cmd.value.tag == CmdTag.Continue:
        loc = function_frame.get_loop_start()
        push_instr(cmd.loc, Bytecode(Opcodes.BRANCH, loc))

    elif cmd.value.tag == CmdTag.Break:
        function_frame.push_loop_break(code.__len__())
        # placeholder, to be replaced when the enclosing while is compiled
        push_instr(cmd.loc, Bytecode(Opcodes.BRANCH, 0))

    elif cmd.value.tag == CmdTag.Exp:
        compile_expression(context, function_frame, code, cmd.value.value)
    else:
        bail("unreachable!")

    return ControlFlowInfo(
        reachable_break,
        terminal_node,
    )


def compile_lvalues(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    lvalues: List[LValue],
) -> None:
    push_instr = make_push_instr(context, code)
    for lvalue_ in reversed(lvalues):
        tag = lvalue_.value.tag
        if tag == LValue_.VAR:
            var = lvalue_.value.value
            loc_idx = function_frame.get_local(var.value)
            push_instr(lvalue_.loc, Bytecode(Opcodes.ST_LOC, loc_idx))
            function_frame.pop()

        elif tag == LValue_.MUTATE:
            e = lvalue_.value.value
            compile_expression(context, function_frame, code, e)
            push_instr(lvalue_.loc, Bytecode(Opcodes.WRITE_REF))
            function_frame.pop()
            function_frame.pop()

        elif tag == LValue_.POP:
            push_instr(lvalue_.loc, Bytecode(Opcodes.POP))
            function_frame.pop()
        else:
            bail("unreachable!")



def infer_int_bin_op_result_ty(
    tys1: List[InferredType],
    tys2: List[InferredType],
) -> InferredType:
    if tys1.__len__() != 1 or tys2.__len__() != 1:
        return InferredType.Anything

    if tys1[0].tag == InferredTypeTag.U8 and tys2[0].tag == InferredTypeTag.U8 :
        return InferredType.U8

    if tys1[0].tag == InferredTypeTag.U64 and tys2[0].tag == InferredTypeTag.U64 :
        return InferredType.U64

    if tys1[0].tag == InferredTypeTag.U128 and tys2[0].tag == InferredTypeTag.U128 :
        return InferredType.U128

    return InferredType.Anything


def compile_expression(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    exp: Exp,
) -> List[InferredType]:
    push_instr = make_push_instr(context, code)
    if isinstance(exp.value, MoveExp):
        v = exp.value.v0
        loc_idx = function_frame.get_local(v.value)
        load_loc = Bytecode(Opcodes.MOVE_LOC, loc_idx)
        push_instr(exp.loc, load_loc)
        function_frame.push()
        loc_type = function_frame.get_local_type(loc_idx)
        return [InferredType.from_signature_token(loc_type)]

    elif isinstance(exp.value, CopyExp):
        v = exp.value.v0
        loc_idx = function_frame.get_local(v.value)
        load_loc = Bytecode(Opcodes.COPY_LOC, loc_idx)
        push_instr(exp.loc, load_loc)
        function_frame.push()
        loc_type = function_frame.get_local_type(loc_idx)
        return [InferredType.from_signature_token(loc_type)]

    elif isinstance(exp.value, BorrowLocalExp):
        is_mutable, v = exp.value.v0
        loc_idx = function_frame.get_local(v.value)
        loc_type = function_frame.get_local_type(loc_idx)
        inner_token = InferredType.from_signature_token(loc_type)
        if is_mutable:
            push_instr(exp.loc, Bytecode(Opcodes.MUT_BORROW_LOC, loc_idx))
            function_frame.push()
            return [InferredType.MutableReference(inner_token)]
        else:
            push_instr(exp.loc, Bytecode(Opcodes.IMM_BORROW_LOC, loc_idx))
            function_frame.push()
            return [InferredType.Reference(inner_token)]

    elif isinstance(exp.value, ValueExp):
        cv_ = exp.value.v0.value
        if cv_.tag == SerializedType.ADDRESS:
            addr_idx = context.address_index(cv_.value)
            push_instr(exp.loc, Bytecode(Opcodes.LD_ADDR, addr_idx))
            function_frame.push()
            return [InferredType.Address]

        elif cv_.tag == SerializedType.U8:
            push_instr(exp.loc, Bytecode(Opcodes.LD_U8, cv_.value))
            function_frame.push()
            return [InferredType.U8]

        elif cv_.tag == SerializedType.U64:
            push_instr(exp.loc, Bytecode(Opcodes.LD_U64, cv_.value))
            function_frame.push()
            return [InferredType.U64]

        elif cv_.tag == SerializedType.U128:
            push_instr(exp.loc, Bytecode(Opcodes.LD_U128, cv_.value))
            function_frame.push()
            return [InferredType.U128]

        elif cv_.tag == SerializedType.BYTEARRAY:
            buf_idx = context.byte_array_index(cv_.value)
            push_instr(exp.loc, Bytecode(Opcodes.LD_BYTEARRAY, buf_idx))
            function_frame.push()
            return [InferredType.ByteArray]

        elif cv_.tag == SerializedType.BOOL:
            if cv_.value:
                bcode = Bytecode(Opcodes.LD_TRUE)
            else:
                bcode = Bytecode(Opcodes.LD_FALSE)

            push_instr(exp.loc, bcode)
            function_frame.push()
            return [InferredType.Bool]

    elif isinstance(exp.value, PackExp):
        (name, tys, fields) = exp.value.v0
        tokens = LocalsSignature(compile_types(context, tys))
        type_actuals_id = context.locals_signature_index(tokens)
        def_idx = context.struct_definition_index(name)

        self_name = SELF_MODULE_NAME
        ident = QualifiedStructIdent(
            self_name,
            name,
        )
        sh_idx = context.struct_handle_index(ident)

        num_fields = fields.__len__()
        for (field_order, (field, e)) in enumerate(fields):
            # Check that the fields are specified in order matching the definition.
            (_, _, decl_order) = context.field(sh_idx, field.value)
            if field_order != decl_order:
                bail("Field {} defined out of order for class {}", field, name)

            compile_expression(context, function_frame, code, e)

        push_instr(exp.loc, Bytecode(Opcodes.PACK, (def_idx, type_actuals_id)))
        for _ in range(num_fields):
            function_frame.pop()

        function_frame.push()
        return [InferredType.Struct(sh_idx)]

    elif isinstance(exp.value, UnaryExp):
        (op, e) = exp.value.v0
        compile_expression(context, function_frame, code, e)
        assert op == UnaryOp.Not
        push_instr(exp.loc, Bytecode(Opcodes.NOT))
        return [InferredType.Bool]

    elif isinstance(exp.value, BinopExp):
        (e1, op, e2) = exp.value.v0
        tys1 = compile_expression(context, function_frame, code, e1)
        tys2 = compile_expression(context, function_frame, code, e2)

        function_frame.pop()

        if op == BinOp.Add:
            push_instr(exp.loc, Bytecode(Opcodes.ADD))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Sub:
            push_instr(exp.loc, Bytecode(Opcodes.SUB))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Mul:
            push_instr(exp.loc, Bytecode(Opcodes.MUL))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Mod:
            push_instr(exp.loc, Bytecode(Opcodes.MOD))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Div:
            push_instr(exp.loc, Bytecode(Opcodes.DIV))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.BitOr:
            push_instr(exp.loc, Bytecode(Opcodes.BIT_OR))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.BitAnd:
            push_instr(exp.loc, Bytecode(Opcodes.BIT_AND))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Xor:
            push_instr(exp.loc, Bytecode(Opcodes.XOR))
            return [infer_int_bin_op_result_ty(tys1, tys2)]

        elif op == BinOp.Shl:
            push_instr(exp.loc, Bytecode(Opcodes.SHL))
            return tys1

        elif op == BinOp.Shr:
            push_instr(exp.loc, Bytecode(Opcodes.SHR))
            return tys1

        elif op == BinOp.Or:
            push_instr(exp.loc, Bytecode(Opcodes.OR))
            return [InferredType.Bool]

        elif op == BinOp.And:
            push_instr(exp.loc, Bytecode(Opcodes.AND))
            return [InferredType.Bool]

        elif op == BinOp.Eq:
            push_instr(exp.loc, Bytecode(Opcodes.EQ))
            return [InferredType.Bool]

        elif op == BinOp.Neq:
            push_instr(exp.loc, Bytecode(Opcodes.NEQ))
            return [InferredType.Bool]

        elif op == BinOp.Lt:
            push_instr(exp.loc, Bytecode(Opcodes.LT))
            return [InferredType.Bool]

        elif op == BinOp.Gt:
            push_instr(exp.loc, Bytecode(Opcodes.GT))
            return [InferredType.Bool]

        elif op == BinOp.Le:
            push_instr(exp.loc, Bytecode(Opcodes.LE))
            return [InferredType.Bool]

        elif op == BinOp.Ge:
            push_instr(exp.loc, Bytecode(Opcodes.GE))
            return [InferredType.Bool]

        elif op == BinOp.Subrange:
            bail("Subrange operators should only appear in specification ASTs.")
        else:
            bail("unreachable!")

    elif isinstance(exp.value, DereferenceExp):
        e = exp.value.v0
        loc_type = compile_expression(context, function_frame, code, e).pop(0)
        push_instr(exp.loc, Bytecode(Opcodes.READ_REF))
        if loc_type.tag == InferredTypeTag.MutableReference or \
            loc_type.tag == InferredTypeTag.Reference:
            return [loc_type.reference]
        else:
            return [InferredType.Anything]

    elif isinstance(exp.value, BorrowExp):
        is_mutable = exp.value.is_mutable
        inner_exp = exp.value.exp
        field = exp.value.field
        loc_type = compile_expression(context, function_frame, code, inner_exp)[0]
        sh_idx = loc_type.get_struct_handle()
        (fd_idx, field_type, _) = context.field(sh_idx, field)
        function_frame.pop()
        inner_token = InferredType.from_signature_token(field_type)
        if is_mutable:
            push_instr(exp.loc, Bytecode(Opcodes.MUT_BORROW_FIELD, fd_idx))
            function_frame.push()
            return [InferredType.MutableReference(inner_token)]
        else:
            push_instr(exp.loc, Bytecode(Opcodes.IMM_BORROW_FIELD, fd_idx))
            function_frame.push()
            return [InferredType.Reference(inner_token)]

    elif isinstance(exp.value, FunctionCallExp):
        (f, exps) = exp.value.v0
        actuals_tys = []
        for types in compile_expression(context, function_frame, code, exps):
            actuals_tys.push_back(types)

        return compile_call(context, function_frame, code, f, actuals_tys)

    elif isinstance(exp.value, ExprListExp):
        exps = exp.value.v0
        result = []
        for e in exps:
            result.append(compile_expression(context, function_frame, code, e))
        return result



def compile_call(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    call: FunctionCall,
    argument_types: List[InferredType],
) -> List[InferredType]:
    push_instr = make_push_instr(context, code)
    if call.value.tag == FunctionCall_.BUILTIN:
        function = call.value.value

        if function.tag == BuiltinTag.GetTxnSender:
            push_instr(call.loc, Bytecode(Opcodes.GET_TXN_SENDER))
            function_frame.push()
            return [InferredType.Address]

        elif function.tag == BuiltinTag.Exists:
            (name, tys) = function.exists
            tokens = LocalsSignature(compile_types(context, tys))
            type_actuals_id = context.locals_signature_index(tokens)
            def_idx = context.struct_definition_index(name)
            push_instr(call.loc, Bytecode(Opcodes.EXISTS, (def_idx, type_actuals_id)))
            function_frame.pop()
            function_frame.push()
            return [InferredType.Bool]

        elif function.tag == BuiltinTag.BorrowGlobal:
            (mut_, name, tys) = function.borrow
            tokens = LocalsSignature(compile_types(context, tys))
            type_actuals_id = context.locals_signature_index(tokens)
            def_idx = context.struct_definition_index(name)
            if mut_:
                bcode = Bytecode(Opcodes.MUT_BORROW_GLOBAL, (def_idx, type_actuals_id))
            else:
                bcode = Bytecode(Opcodes.IMM_BORROW_GLOBAL, (def_idx, type_actuals_id))

            push_instr(call.loc, bcode)
            function_frame.pop()
            function_frame.push()

            self_name = SELF_MODULE_NAME
            ident = QualifiedStructIdent(self_name, name)

            sh_idx = context.struct_handle_index(ident)
            inner = InferredType.Struct(sh_idx)
            if mut_:
                return [InferredType.MutableReference(inner)]
            else:
                return [InferredType.Reference(inner)]

        elif function.tag == BuiltinTag.MoveFrom:
            (name, tys) = function.move
            tokens = LocalsSignature(compile_types(context, tys))
            type_actuals_id = context.locals_signature_index(tokens)
            def_idx = context.struct_definition_index(name)
            push_instr(call.loc, Bytecode(Opcodes.MOVE_FROM, (def_idx, type_actuals_id)))
            function_frame.pop() # pop the address
            function_frame.push() # push the return value

            self_name = SELF_MODULE_NAME
            ident = QualifiedStructIdent(self_name, name)
            sh_idx = context.struct_handle_index(ident)
            return [InferredType.Struct(sh_idx)]

        elif function.tag == BuiltinTag.MoveToSender:
            (name, tys) = function.move
            tokens = LocalsSignature(compile_types(context, tys))
            type_actuals_id = context.locals_signature_index(tokens)
            def_idx = context.struct_definition_index(name)

            push_instr(call.loc, Bytecode(Opcodes.MOVE_TO, (def_idx, type_actuals_id)))
            function_frame.push()
            return []

        elif function.tag == BuiltinTag.Freeze:
            push_instr(call.loc, Bytecode(Opcodes.FREEZE_REF))
            function_frame.pop() # pop ref
            function_frame.push() # push imm ref
            xx = argument_types.pop(0)
            if xx.tag == InferredTypeTag.Reference or xx.tag == InferredTypeTag.MutableReference:
                inner_token = xx.reference
            else:
                # Incorrect call
                inner_token = InferredType.Anything

            return [InferredType.Reference(inner_token)]

        elif function.tag == BuiltinTag.ToU8:
            push_instr(call.loc, Bytecode(Opcodes.CAST_U8))
            function_frame.pop()
            function_frame.push()
            return [InferredType.U8]

        elif function.tag == BuiltinTag.ToU64:
            push_instr(call.loc, Bytecode(Opcodes.CAST_U64))
            function_frame.pop()
            function_frame.push()
            return [InferredType.U64]

        elif function.tag == BuiltinTag.ToU128:
            push_instr(call.loc, Bytecode(Opcodes.CAST_U128))
            function_frame.pop()
            function_frame.push()
            return [InferredType.U128]

    elif call.value.tag == FunctionCall_.MODULE_FUNCTION_CALL:
        module = call.value.value.module
        name = call.value.value.name
        type_actuals = call.value.value.type_actuals

        tokens = LocalsSignature(compile_types(context, type_actuals))
        type_actuals_id = context.locals_signature_index(tokens)
        fh_idx = context.function_handle(module, name)[1]
        fcall = Bytecode(Opcodes.CALL, (fh_idx, type_actuals_id))
        push_instr(call.loc, fcall)
        for _ in range(argument_types.__len__()):
            function_frame.pop()

        # Return value of current function is pushed onto the stack.
        function_frame.push()
        signature = context.function_signature(module, name)#.0
        return [InferredType.from_signature_token(x) for x in signature.return_types]

    else:
        bail("unreachable!")

#**************************************************************************************************
# Bytecode
#**************************************************************************************************

def compile_function_body_bytecode(
    context: Context,
    formals: List[Tuple[Var, Type]],
    localss: List[Tuple[Var, Type]],
    blocks: BytecodeBlocks,
) -> CodeUnit:
    function_frame = FunctionFrame.new()
    locals_signature = LocalsSignature([])
    for (var, t) in formals:
        sig = compile_type(context, t)
        function_frame.define_local(var.value, deepcopy(sig))
        locals_signature.v0.append(sig)
        record_src_loc_local(context, var)

    for (var_, t) in localss:
        sig = compile_type(context, t)
        function_frame.define_local(var_.value, deepcopy(sig))
        locals_signature.v0.append(sig)
        record_src_loc_local(context, var_)

    sig_idx = context.locals_signature_index(locals_signature)

    code = []
    label_to_index: Mapping[Label, Uint16] = {}
    for (label, block) in blocks:
        label_to_index[label] = code.__len__()
        context.label_index(label)
        compile_bytecode_block(context, function_frame, code, block)

    fake_to_actual = context.build_index_remapping(label_to_index)
    remap_branch_offsets(code, fake_to_actual)
    max_stack_size = Uint16.max_value
    return CodeUnit(
        max_stack_size,
        sig_idx,
        code,
    )

def compile_bytecode_block(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    block: BytecodeBlock,
) -> None:
    for instr in block:
        compile_bytecode(context, function_frame, code, instr)


def compile_bytecode(
    context: Context,
    function_frame: FunctionFrame,
    code: List[Bytecode],
    irb: IRBytecode,
) -> None:
    loc, instr_ = irb.loc, irb.value
    push_instr = make_push_instr(context, code)
    if instr_.tag in [
        Opcodes.POP,
        Opcodes.RET,
        Opcodes.CAST_U8,
        Opcodes.CAST_U64,
        Opcodes.CAST_U128,
        Opcodes.LD_TRUE,
        Opcodes.LD_FALSE,
        Opcodes.READ_REF,
        Opcodes.WRITE_REF,
        Opcodes.FREEZE_REF,
        Opcodes.ADD,
        Opcodes.SUB,
        Opcodes.MUL,
        Opcodes.MOD,
        Opcodes.DIV,
        Opcodes.BIT_OR,
        Opcodes.BIT_AND,
        Opcodes.XOR,
        Opcodes.OR,
        Opcodes.AND,
        Opcodes.NOT,
        Opcodes.EQ,
        Opcodes.NEQ,
        Opcodes.LT,
        Opcodes.GT,
        Opcodes.LE,
        Opcodes.GE,
        Opcodes.ABORT,
        Opcodes.GET_TXN_SENDER,
        Opcodes.SHL,
        Opcodes.SHR,
    ]:
        ff_instr = Bytecode(instr_.tag)

    elif instr_.tag in [
        Opcodes.BR_TRUE,
        Opcodes.BR_FALSE,
        Opcodes.BRANCH,
    ]:
        ff_instr = Bytecode(instr_.tag, context.label_index(instr_.value))

    elif instr_.tag in [
        Opcodes.LD_U8,
        Opcodes.LD_U64,
        Opcodes.LD_U128,
    ]:
        ff_instr = Bytecode(instr_.tag, instr_.value)

    elif instr_.tag in [
        Opcodes.COPY_LOC,
        Opcodes.MOVE_LOC,
        Opcodes.ST_LOC,
        Opcodes.MUT_BORROW_LOC,
        Opcodes.IMM_BORROW_LOC,
    ]:
        v_ = instr_.value.value
        ff_instr = Bytecode(instr_.tag, function_frame.get_local(v_))

    elif instr_.tag == Opcodes.LD_BYTEARRAY:
        ff_instr = Bytecode(instr_.tag, context.byte_array_index(instr_.value))

    elif instr_.tag == Opcodes.LD_ADDR:
        ff_instr = Bytecode(instr_.tag, context.address_index(instr_.value))

    elif instr_.tag == Opcodes.CALL:
        (m, n, tys) = instr_.value
        tokens = LocalsSignature(compile_types(context, tys))
        type_actuals_id = context.locals_signature_index(tokens)
        fh_idx = context.function_handle(m, n)[1]
        ff_instr = Bytecode(instr_.tag, (fh_idx, type_actuals_id))

    elif instr_.tag in [
        Opcodes.PACK,
        Opcodes.UNPACK,
        Opcodes.MUT_BORROW_GLOBAL,
        Opcodes.IMM_BORROW_GLOBAL,
        Opcodes.MOVE_FROM,
        Opcodes.MOVE_TO,
        Opcodes.EXISTS,
    ]:
        (n, tys) = instr_.value
        tokens = LocalsSignature(compile_types(context, tys))
        type_actuals_id = context.locals_signature_index(tokens)
        def_idx = context.struct_definition_index(n)
        ff_instr = Bytecode(instr_.tag, (def_idx, type_actuals_id))


    elif instr_.tag in [
        Opcodes.MUT_BORROW_FIELD,
        Opcodes.IMM_BORROW_FIELD,
    ]:
        (name, field) = instr_.value
        field_ = field.value
        qualified_struct_name = QualifiedStructIdent(SELF_MODULE_NAME, name)
        sh_idx = context.struct_handle_index(qualified_struct_name)
        (fd_idx, _, _) = context.field(sh_idx, field_)
        ff_instr = Bytecode(instr_.tag, fd_idx)

    else:
        bail("unreachable!")
    push_instr(loc, ff_instr)



def remap_branch_offsets(code: List[Bytecode], fake_to_actual: Mapping[Uint16, Uint16]):
    for instr in code:
        if instr.tag in [
            Opcodes.BR_TRUE,
            Opcodes.BR_FALSE,
            Opcodes.BRANCH,
        ]:
            instr.value = fake_to_actual[instr.value]

