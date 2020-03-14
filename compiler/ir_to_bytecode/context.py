from __future__ import annotations
from libra.account_address import Address
from compiler.bytecode_source_map.source_map import ModuleSourceMap
from move_core.types.identifier import IdentStr, Identifier
from move_ir.types.ast import *
from move_ir.types.location import *
from libra_vm.file_format import (
        AddressPoolIndex, ByteArrayPoolIndex, CodeOffset, FieldDefinitionIndex,
        FunctionDefinitionIndex, FunctionHandle, FunctionHandleIndex, FunctionSignature,
        FunctionSignatureIndex, IdentifierIndex, Kind, LocalsSignature, LocalsSignatureIndex,
        ModuleHandle, ModuleHandleIndex, SignatureToken, StructDefinitionIndex, StructHandle,
        StructHandleIndex, TableIndex, TypeSignature, TypeSignatureIndex, ModuleAccess
    )
from libra_vm import signature_token_help
from typing import List, Optional, Tuple, Mapping
from dataclasses import dataclass
from libra.rustlib import bail, ensure, usize
from canoser import Uint16
from copy import deepcopy


TypeFormalMap = Mapping[TypeVar_, TableIndex]


def get_or_add_item_macro(m, k_get, k_insert):
    k_key = k_get
    if k_key in m:
        return m.get(k_key)
    else:
        length = len(m)
        if length >= TABLE_MAX_SIZE:
            bail("Max table size reached!")
        m[k_insert] = length
        return length



TABLE_MAX_SIZE = Uint16.max_value

def get_or_add_item_ref(
    m: Mapping[Any, TableIndex],
    k: Any,
) -> TableIndex:
    return get_or_add_item_macro(m, k, k)


def get_or_add_item(m: Mapping[Any, TableIndex], k: Any) -> TableIndex:
    return get_or_add_item_macro(m, k, k)


def ident_str(s: str) -> IdentStr:
    return s

@dataclass
class CompiledDependency:
    structs: Mapping[Tuple[IdentStr, IdentStr], TableIndex]
    functions: Mapping[IdentStr, TableIndex]
    module_pool: List[ModuleHandle]
    struct_pool: List[StructHandle]
    function_signatuire_pool: List[FunctionSignature]
    identifiers: List[Identifier]
    address_pool: List[Address]

    @classmethod
    def new(cls, dep: ModuleAccess) -> CompiledDependency:
        structs = {}
        functions = {}

        for shandle in dep.struct_handles():
            mhandle = dep.module_handle_at(shandle.module)
            mname = dep.identifier_at(mhandle.name)
            sname = dep.identifier_at(shandle.name)
            # get_or_add_item gets the proper class handle index, as `dep.struct_handles()` is
            # properly ordered
            get_or_add_item(structs, (mname, sname))


        # keep only functions defined in the current module
        # with module handle 0
        defined_function_handles = [x for x in dep.function_handles() if x.module.v0 == 0]

        for fhandle in defined_function_handles:
            fname = dep.identifier_at(fhandle.name)
            functions[fname] = fhandle.signature.v0

        return cls(
            structs,
            functions,
            dep.module_handles(),
            dep.struct_handles(),
            dep.function_signatures(),
            dep.identifiers(),
            dep.address_pool(),
        )


    def source_struct_info(
        self,
        idx: StructHandleIndex,
    ) -> Optional[Tuple[QualifiedModuleIdent, StructName]]:
        handle = self.struct_pool[idx.v0]
        module_handle = self.module_pool[handle.module.v0]
        address = self.address_pool[module_handle.address.v0]
        module: ModuleName = self.identifiers[module_handle.name.v0]

        assert(module != SELF_MODULE_NAME)
        ident = QualifiedModuleIdent(
            address = address,
            name = module,
        )
        name: StructName = self.identifiers[handle.name.v0]
        return (ident, name)


    def struct_handle(self, name: QualifiedStructIdent) -> Optional[StructHandle]:
        table_idx = self.structs.get((name.module, name.name))
        if table_idx is not None:
            return self.struct_pool[table_idx]
        else:
            return None


    def function_signature(self, name: FunctionName) -> Optional[FunctionSignature]:
        table_idx = self.functions.get(name)
        if table_idx is not None:
            return self.function_signatuire_pool[table_idx]
        else:
            return None


# Represents all of the pools to be used in the file format, both by CompiledModule
# and CompiledScript.
@dataclass
class MaterializedPools:
    # Module handle pool
    module_handles: List[ModuleHandle]
    # Struct handle pool
    struct_handles: List[StructHandle]
    # Function handle pool
    function_handles: List[FunctionHandle]
    # Type signature pool
    type_signatures: List[TypeSignature]
    # Function signature pool
    function_signatures: List[FunctionSignature]
    # Locals signatures pool
    locals_signatures: List[LocalsSignature]
    # Identifier pool
    identifiers: List[Identifier]
    # Byte array pool
    byte_array_pool: List[ByteArray]
    # Address pool
    address_pool: List[Address]


# Compilation context for a single compilation unit (module or script).
# Contains all of the pools as they are built up.
# Specific definitions to CompiledModule or CompiledScript are not stored.
# However, some fields, like struct_defs and fields, are not used in CompiledScript.
@dataclass
class Context:
    dependencies: Mapping[QualifiedModuleIdent, CompiledDependency]

    # helpers
    aliases: Mapping[QualifiedModuleIdent, ModuleName]
    modules: Mapping[ModuleName, Tuple[QualifiedModuleIdent, ModuleHandle]]
    structs: Mapping[QualifiedStructIdent, StructHandle]
    struct_defs: Mapping[StructName, TableIndex]
    labels: Mapping[Label, Uint16]

    # queryable pools
    fields: Mapping[(StructHandleIndex, Field_), (TableIndex, SignatureToken, usize)]
    function_handles: \
        Mapping[Tuple[ModuleName, FunctionName], Tuple[FunctionHandle, FunctionHandleIndex]]
    function_signatures: \
        Mapping[Tuple[ModuleName, FunctionName], Tuple[FunctionSignature, FunctionSignatureIndex]]

    # Simple pools
    function_signature_pool: Mapping[FunctionSignature, TableIndex]
    module_handles: Mapping[ModuleHandle, TableIndex]
    struct_handles: Mapping[StructHandle, TableIndex]
    type_signatures: Mapping[TypeSignature, TableIndex]
    locals_signatures: Mapping[LocalsSignature, TableIndex]
    identifiers: Mapping[Identifier, TableIndex]
    byte_array_pool: Mapping[ByteArray, TableIndex]
    address_pool: Mapping[Address, TableIndex]

    # Current generic/type formal context
    type_formals: TypeFormalMap

    # The current function index that we are on
    current_function_index: FunctionDefinitionIndex

    # Source location mapping for this module
    source_map: ModuleSourceMap


    # Given the dependencies and the current module, creates an empty context.
    # The current module is a dummy `Self` for CompiledScript.
    # It initializes an "import" of `Self` as the alias for the current_module.
    @classmethod
    def new(cls,
        dependencies_iter: Iterator[ModuleAccess],
        current_module: QualifiedModuleIdent,
    ) -> Context:
        dependencies = {
            QualifiedModuleIdent(dep.name(), dep.address()) : CompiledDependency.new(dep) \
            for dep in dependencies_iter
        }

        context = cls(
            dependencies= dependencies,
            aliases= {},
            modules= {},
            structs= {},
            struct_defs= {},
            labels= {},
            fields= {},
            function_handles= {},
            function_signatures= {},
            function_signature_pool= {},
            module_handles= {},
            struct_handles= {},
            type_signatures= {},
            locals_signatures= {},
            identifiers= {},
            byte_array_pool= {},
            address_pool= {},
            type_formals= {},
            current_function_index= FunctionDefinitionIndex(0),
            source_map= ModuleSourceMap.new(deepcopy(current_module)),
        )
        context.declare_import(current_module, SELF_MODULE_NAME)
        return context


    @classmethod
    def materialize_pool(cls,
        size: usize,
        items: Iterator[Tuple[Any, TableIndex]],
    ) -> List[Any]:
        options = [None] * size
        for (item, idx) in items.items():
            assert(options[idx] is None)
            options[idx] = item

        return options


    @classmethod
    def materialize_map(cls, m: Mapping[T, TableIndex]) -> List[T]:
        return cls.materialize_pool(m.__len__(), m)


    # Finish compilation, and materialize the pools for file format.
    def materialize_pools(self) -> Tuple[MaterializedPools, ModuleSourceMap]:
        cls = self.__class__
        num_functions = self.function_handles.__len__()
        assert(num_functions == self.function_signatures.__len__())
        function_handles = cls.materialize_pool(
            num_functions,
            {t: idx.v0 for (_, (t, idx)) in self.function_handles.items()},
        )
        materialized_pools = MaterializedPools(
            function_handles= function_handles,
            function_signatures= cls.materialize_map(self.function_signature_pool),
            module_handles= cls.materialize_map(self.module_handles),
            struct_handles= cls.materialize_map(self.struct_handles),
            type_signatures= cls.materialize_map(self.type_signatures),
            locals_signatures= cls.materialize_map(self.locals_signatures),
            identifiers= cls.materialize_map(self.identifiers),
            byte_array_pool= cls.materialize_map(self.byte_array_pool),
            address_pool= cls.materialize_map(self.address_pool),
        )
        return (materialized_pools, self.source_map)


    # Bind the type formals into a "pool" for the current context.
    def bind_type_formals(self, m: Mapping[TypeVar_, usize]) -> None:
        for (k, idx) in m.items():
            if idx > TABLE_MAX_SIZE:
                bail("Too many type parameters")

        self.type_formals = deepcopy(m)


    def build_index_remapping(
        self,
        label_to_index: Mapping[Label, Uint16],
    ) -> Mapping[Uint16, Uint16]:
        labels = self.labels
        self.labels = {}
        return {labels[lbl] : actual_idx for (lbl, actual_idx) in label_to_index.items()}


    #**********************************************************************************************
    # Pools
    #**********************************************************************************************

    # Get the alias for the identifier, fails if it is not bound.
    def module_alias(self, ident: QualifiedModuleIdent) -> ModuleName:
        if ident not in self.aliases:
            bail("Missing import for module {}", ident)
        return self.aliases.get(ident)



    # Get the handle for the alias, fails if it is not bound.
    def module_handle(self, module_name: ModuleName) -> ModuleHandle:
        ret = self.modules.get(module_name)
        if ret is None:
            bail("Unbound module alias {}", module_name)
        else:
            (_, mh) = ret
            return mh



    # Get the identifier for the alias, fails if it is not bound.
    def module_ident(self, module_name: ModuleName) -> QualifiedModuleIdent:
        ret = self.modules.get(module_name)
        if ret is None:
            bail("Unbound module alias {}", module_name)
        else:
            (qid, _) = ret
            return qid


    # Get the module handle index for the alias, fails if it is not bound.
    def module_handle_index(self, module_name: ModuleName) -> ModuleHandleIndex:
        return ModuleHandleIndex(self.module_handles[self.module_handle(module_name)])



    # Get the type formal index, fails if it is not bound.
    def type_formal_index(self, t: TypeVar_) -> TableIndex:
        ret = self.type_formals.get(t)
        if ret is None:
            bail("Unbound type parameter {}", t),
        return ret

    # Get the fake offset for the label. Labels will be fixed to real offsets after compilation
    def label_index(self, label: Label) -> CodeOffset:
        return get_or_add_item(self.labels, label)


    # Get the address pool index, adds it if missing.
    def address_index(self, addr: Address) -> AddressPoolIndex:
        return AddressPoolIndex(get_or_add_item(
            self.address_pool,
            addr,
        ))


    # Get the identifier pool index, adds it if missing.
    def identifier_index(self, s: str) -> IdentifierIndex:
        if not isinstance(s, str):
            breakpoint()
        ident = ident_str(s)
        m = self.identifiers
        idx: TableIndex = get_or_add_item_macro(m, ident, ident)
        return IdentifierIndex(idx)


    # Get the byte array pool index, adds it if missing.
    def byte_array_index(self, byte_array: ByteArray) -> ByteArrayPoolIndex:
        return ByteArrayPoolIndex(get_or_add_item_ref(
            self.byte_array_pool,
            byte_array,
        ))


    # Get the field index, fails if it is not bound.
    def field(
        self,
        s: StructHandleIndex,
        f: Field_,
    ) -> Tuple[FieldDefinitionIndex, SignatureToken, usize]:
        ret = self.fields.get((s, f))
        if ret is None:
            bail("Unbound field {}", f)
        else:
            (idx, token, decl_order) = ret
            return (FieldDefinitionIndex(idx), deepcopy(token), decl_order)


    # Get the type signature index, adds it if it is not bound.
    def type_signature_index(self, token: SignatureToken) -> TypeSignatureIndex:
        return TypeSignatureIndex(get_or_add_item(
            self.type_signatures,
            TypeSignature(token),
        ))


    # Get the class definition index, fails if it is not bound.
    def struct_definition_index(self, s: StructName) -> StructDefinitionIndex:
        ret = self.struct_defs.get(s)
        if ret is None:
            bail("Missing class definition for {}", s)
        else:
            return StructDefinitionIndex(ret)


    # Get the locals signature pool index, adds it if missing.
    def locals_signature_index(
        self,
        localss: LocalsSignature,
    ) -> LocalsSignatureIndex:
        return LocalsSignatureIndex(get_or_add_item(
            self.locals_signatures,
            localss,
        ))


    def set_function_index(self, index: TableIndex):
        self.current_function_index = FunctionDefinitionIndex(index)


    def current_function_definition_index(self) -> FunctionDefinitionIndex:
        return self.current_function_index


    def current_struct_definition_index(self) -> StructDefinitionIndex:
        idx = self.struct_defs.__len__()
        return StructDefinitionIndex(idx)


    #**********************************************************************************************
    # Declarations
    #**********************************************************************************************

    # Add an import. This creates a module handle index for the imported module.
    def declare_import(
        self,
        qid: QualifiedModuleIdent,
        alias: ModuleName,
    ) -> ModuleHandleIndex:
        # We don't care about duplicate aliases, if they exist
        self.aliases[qid] = alias
        address = self.address_index(qid.address)
        name = self.identifier_index(qid.name)
        self.modules[alias] = (qid, ModuleHandle(address, name))
        return ModuleHandleIndex(get_or_add_item_ref(
            self.module_handles,
            self.modules.get(alias)[1],
        ))


    # Given an identifier and basic "signature" information, creates a class handle
    # and adds it to the pool.
    def declare_struct_handle_index(
        self,
        sname: QualifiedStructIdent,
        is_nominal_resource: bool,
        type_formals: List[Kind],
    ) -> StructHandleIndex:
        module = self.module_handle_index(sname.module)
        name = self.identifier_index(sname.name)
        self.structs[sname] = StructHandle(
                module,
                name,
                is_nominal_resource,
                type_formals,
            )
        return StructHandleIndex(get_or_add_item_ref(
            self.struct_handles,
            self.structs.get(sname),
        ))


    # Given an identifier, declare the class definition index.
    def declare_struct_definition_index(
        self,
        s: StructName,
    ) -> StructDefinitionIndex:
        idx = self.struct_defs.__len__()
        if idx > TABLE_MAX_SIZE:
            bail("too many class definitions {}", s)

        # TODO: Add the decl of the class definition name here
        # need to handle duplicates
        if s not in self.struct_defs:
            self.struct_defs[s] = idx

        return StructDefinitionIndex(self.struct_defs[s])



    # Given an identifier and a signature, creates a function handle and adds it to the pool.
    # Finds the index for the signature, or adds it to the pool if an identical one has not yet
    # been used.
    def declare_function(
        self,
        mname: ModuleName,
        fname: FunctionName,
        signature: FunctionSignature,
    ) -> None:
        m_f = (mname, fname)
        module = self.module_handle_index(mname)
        name = self.identifier_index(fname)

        sidx = get_or_add_item_ref(self.function_signature_pool, signature)
        signature_index = FunctionSignatureIndex(sidx)
        self.function_signatures[m_f] = (signature, signature_index)

        handle = FunctionHandle(
            module,
            name,
            signature_index,
        )
        # handle duplicate declarations
        # erroring on duplicates needs to be done by the bytecode verifier
        fhh = self.function_handles.get(m_f)
        if fhh is None:
            hidx = self.function_handles.__len__()
        else:
            (_, idx) = fhh
            hidx = idx.v0

        if hidx > TABLE_MAX_SIZE:
            bail("too many functions: {}.{}", mname, fname)

        handle_index = FunctionHandleIndex(hidx)
        self.function_handles[m_f] = (handle, handle_index)



    # Given a class handle and a field, adds it to the pool.
    def declare_field(
        self,
        s: StructHandleIndex,
        f: Field_,
        token: SignatureToken,
        decl_order: usize,
    ) -> FieldDefinitionIndex:
        idx = self.fields.__len__()
        if idx > TABLE_MAX_SIZE:
            bail("too many fields: {}.{}", s, f)

        # need to handle duplicates
        if (s, f) not in self.fields:
            self.fields[(s, f)] = (idx, token, decl_order)
        return FieldDefinitionIndex(self.fields[(s, f)][0])



    #**********************************************************************************************
    # Dependency Resolution
    #**********************************************************************************************

    def dependency(self, m: QualifiedModuleIdent) -> CompiledDependency:
        ret = self.dependencies.get(m)
        if ret is None:
            bail("Dependency not provided for {}", m)
        return ret


    def dep_struct_handle(self, s: QualifiedStructIdent) -> Tuple[bool, List[Kind]]:
        if s.module == SELF_MODULE_NAME:
            bail("Unbound class {}", s)

        mident = self.module_ident(s.module)
        dep = self.dependency(mident)
        shandle = dep.struct_handle(s)
        if shandle is None:
            bail("Unbound class {}", s)
        else:
            return (shandle.is_nominal_resource, deepcopy(shandle.type_formals))



    # Given an identifier, find the class handle index.
    # Creates the handle and adds it to the pool if it it is the *first* time it looks
    # up the class in a dependency.
    def struct_handle_index(self, s: QualifiedStructIdent) -> StructHandleIndex:
        sh = self.structs.get(s)
        if sh is not None:
            return StructHandleIndex(self.struct_handles.get(sh))
        else:
            (is_nominal_resource, type_formals) = self.dep_struct_handle(s)
            return self.declare_struct_handle_index(s, is_nominal_resource, type_formals)



    def reindex_signature_token(
        self,
        dep: QualifiedModuleIdent,
        orig: SignatureToken,
    ) -> SignatureToken:
        if orig.tag in [
            SerializedType.BOOL,
            SerializedType.U8,
            SerializedType.U64,
            SerializedType.U128,
            SerializedType.BYTEARRAY,
            SerializedType.ADDRESS,
            SerializedType.TYPE_PARAMETER,
        ]:
             return orig

        elif orig.tag == SerializedType.VECTOR:
            inner = orig.vector_type
            correct_inner = self.reindex_signature_token(dep, inner)
            return signature_token_help.Vector(correct_inner)

        elif orig.tag == SerializedType.REFERENCE:
            inner = orig.reference
            correct_inner = self.reindex_signature_token(dep, inner)
            return signature_token_help.Reference(correct_inner)

        elif orig.tag == SerializedType.MUTABLE_REFERENCE:
            inner = orig.reference
            correct_inner = self.reindex_signature_token(dep, inner)
            return signature_token_help.MutableReference(correct_inner)

        elif orig.tag == SerializedType.STRUCT:
            (orig_sh_idx, inners) = orig.struct
            dep_info = self.dependency(dep)
            (mident, sname) = dep_info.source_struct_info(orig_sh_idx)
                # .ok_or_else(|format_err!("Malformed dependency"))

            module_name = self.module_alias(mident)
            sident = QualifiedStructIdent(module_name, sname)

            correct_sh_idx = self.struct_handle_index(sident)
            correct_inners = [self.reindex_signature_token(dep, t) for t in inners]
            return signature_token_help.Struct((correct_sh_idx, correct_inners))



    def reindex_function_signature(
        self,
        dep: QualifiedModuleIdent,
        orig: FunctionSignature,
    ) -> FunctionSignature:
        return_types = [self.reindex_signature_token(dep, t) for t in orig.return_types]
        arg_types = [self.reindex_signature_token(dep, t) for t in orig.arg_types]
        type_formals = orig.type_formals
        return FunctionSignature(
            return_types,
            arg_types,
            type_formals,
        )


    def dep_function_signature(
        self,
        m: ModuleName,
        f: FunctionName,
    ) -> FunctionSignature:
        if m == SELF_MODULE_NAME:
            bail("Unbound function {}.{}", m, f)

        mident = self.module_ident(m)
        dep = self.dependency(mident)
        sig = dep.function_signature(f)
        if sig is None:
            bail("Unbound function {}.{}", m, f)
        else:
            return self.reindex_function_signature(mident, sig)



    def ensure_function_declared(self, m: ModuleName, f: FunctionName) -> None:
        m_f = (m, f)
        if m_f not in self.function_handles:
            assert(m_f not in self.function_signatures)
            sig = self.dep_function_signature(m, f)
            self.declare_function(m, f, sig)

        assert(m_f in self.function_handles)
        assert(m_f in self.function_signatures)


    # Given an identifier, find the function handle and its index.
    # Creates the handle+signature and adds it to the pool if it it is the *first* time it looks
    # up the function in a dependency.
    def function_handle(
        self,
        m: ModuleName,
        f: FunctionName,
    ) -> Tuple[FunctionHandle, FunctionHandleIndex]:
        self.ensure_function_declared(m, f)
        return self.function_handles.get((m, f))


    # Given an identifier, find the function signature and its index.
    # Creates the handle+signature and adds it to the pool if it it is the *first* time it looks
    # up the function in a dependency.
    def function_signature(
        self,
        m: ModuleName,
        f: FunctionName,
    ) -> Tuple[FunctionSignature, FunctionSignatureIndex]:
        self.ensure_function_declared(m, f)
        return self.function_signatures.get((m, f))
