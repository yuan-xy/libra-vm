from __future__ import annotations
from mol.bytecode_verifier import VerifiedModule
from mol.move_core.types.identifier import IdentStr, Identifier
from libra.vm_error import StatusCode, VMStatus
from mol.vm.file_format import (
    Bytecode, CodeUnit, FunctionDefinitionIndex, FunctionHandle, FunctionSignature,
    CompiledModule, FieldDefinitionIndex, StructDefinitionIndex,
    StructFieldInformation, TableIndex,
    ModuleAccess
    )
from mol.vm.file_format_common import Opcodes, SerializedType, SerializedNativeStructFlag
from mol.vm.internals import ModuleIndex
from mol.vm.vm_exception import VMException
from mol.move_vm.types.loaded_data import StructDef
from mol.move_core import JsonPrintable
from typing import List, Optional, Mapping, Any
from dataclasses import dataclass
import abc
from libra.rustlib import bail, usize, format_str
from canoser import Uint8
from copy import deepcopy

# Loaded representation for function definitions and handles.


# Trait that defines the internal representation of a move function.
class FunctionReference(abc.ABC):
    # Create a new function reference to a module
    @classmethod
    @abc.abstractmethod
    def new(cls, module: LoadedModule, idx: FunctionDefinitionIndex) -> FunctionReference:
        pass

    # Fetch the reference to the module where the function is defined
    @abc.abstractmethod
    def module(self) -> LoadedModule:
        pass

    # Fetch the code of the function definition
    @abc.abstractmethod
    def code_definition(self) -> List[Bytecode]:
        pass

    # Return the number of locals for the function
    @abc.abstractmethod
    def local_count(self) -> usize:
        pass

    # Return the number of input parameters for the function
    @abc.abstractmethod
    def arg_count(self) -> usize:
        pass

    # Return the number of output parameters for the function
    @abc.abstractmethod
    def return_count(self) -> usize:
        pass

    # Return whether the function is native or not
    @abc.abstractmethod
    def is_native(self) -> bool:
        pass

    # Return the name of the function
    @abc.abstractmethod
    def name(self) -> IdentStr:
        pass

    # Returns the signature of the function
    @abc.abstractmethod
    def signature(self) -> FunctionSignature:
        pass


# Resolved form of a function handle
@dataclass
class FunctionRef(FunctionReference):
    amodule: LoadedModule #field 'module' with collid with 'module' method in FunctionReference
    fdef: FunctionDef
    handle: FunctionHandle

    def __str__(self):
        return self.pretty_string()

    @classmethod
    def new(cls, module: LoadedModule, idx: FunctionDefinitionIndex) -> FunctionRef:
        fdef = module.f_defs[idx.into_index()]
        fn_definition = module.function_def_at(idx)
        handle = module.function_handle_at(fn_definition.function)
        return FunctionRef(module, fdef, handle)


    def module(self) -> LoadedModule:
        return self.amodule


    def code_definition(self) -> List[Bytecode]:
        return self.fdef.code


    def local_count(self) -> usize:
        return self.fdef.local_count


    def arg_count(self) -> usize:
        return self.fdef.arg_count


    def return_count(self) -> usize:
        return self.fdef.return_count


    def is_native(self) -> bool:
        return (self.fdef.flags & CodeUnit.NATIVE) == CodeUnit.NATIVE


    def name(self) -> IdentStr:
        return self.amodule.identifier_at(self.handle.name)


    def signature(self) -> FunctionSignature:
        return self.amodule.function_signature_at(self.handle.signature)


    def pretty_string(self) -> str:
        signature = self.signature()
        return format_str(
            "{}.{}({}){}",
            self.module().name(),
            self.name(),
            signature.arg_types,
            signature.return_types
        )

# Resolved form of a function definition
@dataclass
class FunctionDef(JsonPrintable):
    local_count: usize
    arg_count: usize
    return_count: usize
    code: List[Bytecode]
    flags: Uint8

    @classmethod
    def new(cls, module: VerifiedModule, idx: FunctionDefinitionIndex) -> FunctionDef:
        definition = module.function_def_at(idx)
        code = deepcopy(definition.code.code)
        handle = module.function_handle_at(definition.function)
        function_sig = module.function_signature_at(handle.signature)
        flags = definition.flags
        # Local count for native function is omitted
        if (flags & CodeUnit.NATIVE) == CodeUnit.NATIVE:
            local_count = 0
        else:
            local_count = module.locals_signature_at(definition.code.locals).v0.__len__()

        return FunctionDef(
            local_count,
            function_sig.arg_types.__len__(),
            function_sig.return_types.__len__(),
            code,
            flags,
        )



# Defines a loaded module in the memory. Currently we just store module itself with a bunch of
# reverse mapping that allows querying definition of struct/function by name.
@dataclass
class LoadedModule(ModuleAccess, JsonPrintable):
    module: VerifiedModule

    struct_defs_table: Mapping[Identifier, StructDefinitionIndex]

    field_defs_table: Mapping[Identifier, FieldDefinitionIndex]

    function_defs_table: Mapping[Identifier, FunctionDefinitionIndex]

    f_defs: List[FunctionDef] #field 'function_defs' collid with 'function_defs' method in ModuleAccess

    field_offsets: List[TableIndex]

    cache: LoadedModuleCache


    def as_module(self) -> CompiledModule:
        return self.module.as_inner()

    @classmethod
    def new(cls, module: VerifiedModule) -> LoadedModule:
        if not isinstance(module, VerifiedModule):
            bail(f"Not a VerifiedModule: {type(module)}")
        struct_defs_table = {}
        field_defs_table = {}
        function_defs_table = {}
        function_defs = []

        struct_defs = [None for _x in module.struct_defs()]
        cache = LoadedModuleCache(struct_defs)

        field_offsets: List[TableIndex] = [0 for _x in module.field_defs()]

        for (idx, struct_def) in enumerate(module.struct_defs()):
            name = module.identifier_at(module.struct_handle_at(struct_def.struct_handle).name)
            sd_idx = StructDefinitionIndex.new(idx)
            struct_defs_table[name] = sd_idx

            if struct_def.field_information.tag == SerializedNativeStructFlag.DECLARED:
                field_count = struct_def.field_information.field_count
                fields = struct_def.field_information.fields
                for i in range(field_count):
                    field_index = fields.into_index()
                    # Implication of module verification `member_struct_defs` check
                    assert (field_index <= usize.max_value - i)
                    field_offsets[field_index + i] = i


        for (idx, field_def) in enumerate(module.field_defs()):
            name = module.identifier_at(field_def.name)
            fd_idx = FieldDefinitionIndex.new(idx)
            field_defs_table[name] = fd_idx

        for (idx, function_def) in enumerate(module.function_defs()):
            name = module\
                .identifier_at(module.function_handle_at(function_def.function).name)
            fd_idx = FunctionDefinitionIndex.new(idx)
            function_defs_table[name] = fd_idx
            # `function_defs` is initally empty, a single element is pushed per loop iteration and
            # the number of iterations is bound to the max size of `module.function_defs()`
            # MIRAI currently cannot work with a bound based on the length of
            # `module.function_defs()`.
            assert (function_defs.__len__() < usize.max_value)
            function_defs.append(FunctionDef.new(module, fd_idx))

        return LoadedModule(
            module,
            struct_defs_table,
            field_defs_table,
            function_defs_table,
            function_defs,
            field_offsets,
            cache,
        )


    # Return a cached copy of the class def at this index, if available.
    def cached_struct_def_at(self, idx: StructDefinitionIndex) -> Optional[StructDef]:
        cached = self.cache.struct_defs[idx.into_index()]
        return deepcopy(cached)


    # Cache this class def at this location.
    def cache_struct_def(self, idx: StructDefinitionIndex, sdef: StructDef):
        self.cache.struct_defs[idx.into_index()] = sdef
        # XXX If multiple writers call this at the same time, the last write wins. Is this
        # desirable


    def get_field_offset(self, idx: FieldDefinitionIndex) -> TableIndex:
        try:
            ret = self.field_offsets[idx.into_index()]
            if ret is not None:
                return ret
        except IndexError:
            pass
        raise VMException(VMStatus(StatusCode.LINKER_ERROR))


    def get_struct_def_index(self, struct_name: IdentStr) -> StructDefinitionIndex:
        try:
            ret = self.struct_defs_table[struct_name]
            if ret is not None:
                return ret
        except IndexError:
            pass
        raise VMException(VMStatus(StatusCode.LINKER_ERROR))


@dataclass
class LoadedModuleCache:
    # TODO: this can probably be made lock-free by using AtomicPtr or the "atom" crate. Consider
    # doing so in the future.
    struct_defs: List[Optional[StructDef]] #TTODO: do we need RwLock in python


# impl PartialEq for LoadedModuleCache {
#     def eq(self, _other: &Self) -> bool {
#         # This is a cache so ignore equality checks.
#         True
#     }
# }

