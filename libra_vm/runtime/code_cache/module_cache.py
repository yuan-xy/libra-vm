from __future__ import annotations
from libra_vm.runtime.execution_context import InterpreterContext
from libra_vm.runtime.loaded_data import FunctionRef, FunctionReference, LoadedModule
from bytecode_verifier import VerifiedModule

from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus
from libra_vm.vm_exception import VMException
from libra_vm.errors import *
from libra_vm.file_format import (
        FunctionHandleIndex, SignatureToken, StructDefinitionIndex, StructFieldInformation,
        StructHandleIndex, CompiledModule, ModuleAccess
    )
from libra_vm.file_format_common import Opcodes, SerializedType, SerializedNativeStructFlag
from libra_vm.views import FunctionHandleView, StructHandleView
from libra_vm.runtime_types.loaded_data import StructDef, Type
from libra_vm.runtime_types.native_structs import resolve_native_struct
from libra_vm.runtime_types.type_context import TypeContext
from typing import List, Optional, Mapping
from dataclasses import dataclass, field
from copy import deepcopy
# Cache for modules published on chain.



# Cache for modules that resides in a VM. It is an internally mutable map from module
# identifier to a reference to loaded module, where the actual module is owned by the Arena
# allocator so that it will guarantee to outlive the lifetime of the transaction.
@dataclass
class VMModuleCache:
    cmap: Mapping[ModuleId, LoadedModule] = field(default_factory=dict)


    # Given a function handle index, resolves that handle into an internal representation of
    # move function.
    #
    # Returns:
    #
    # * `FunctionRef` if such function exists.
    # * `Err(...)` for a verification issue in a resolved dependency, VM invariant violation, or
    #   function not found.
    def resolve_function_ref(
        self,
        caller_module: LoadedModule,
        idx: FunctionHandleIndex,
        data_view: InterpreterContext,
    ) -> FunctionRef:
        function_handle = caller_module.function_handle_at(idx)
        callee_name = caller_module.identifier_at(function_handle.name)
        callee_module_id = FunctionHandleView(caller_module, function_handle).module_id()

        callee_module = self.get_loaded_module(callee_module_id, data_view)
        if callee_name in callee_module.function_defs_table:
            callee_func_id = callee_module.function_defs_table[callee_name]
            return FunctionRef.new(callee_module, callee_func_id)
        else:
            raise VMException(VMStatus(StatusCode.LINKER_ERROR))


    # Resolve a StructDefinitionIndex into a StructDef. This process will be recursive so we may
    # charge gas on each recursive step.
    #
    # Returns:
    #
    # * `StructDef` if such class exists.
    # * `Err(...)` for a verification or other issue in a resolved dependency, out of gas, or for
    #   a VM invariant violation.
    def resolve_struct_def(
        self,
        module: LoadedModule,
        idx: StructDefinitionIndex,
        data_view: InterpreterContext,
    ) -> StructDef:
        sdef = module.cached_struct_def_at(idx)
        if sdef is not None:
            return sdef

        struct_def = module.struct_def_at(idx)
        struct_handle = module.struct_handle_at(struct_def.struct_handle)
        type_context =\
            TypeContext.identity_mapping(struct_handle.type_formals.__len__())

        if struct_def.field_information.tag == SerializedNativeStructFlag.NATIVE:
            struct_name = module.identifier_at(struct_handle.name)
            struct_def_module_id =\
                StructHandleView(module, struct_handle).module_id()
            native_struct = resolve_native_struct(struct_def_module_id, struct_name)
            if native_struct is not None:
                sdef = StructDef('Native', deepcopy(native_struct.struct_type))
            else:
                raise VMException(VMStatus(StatusCode.LINKER_ERROR))
        elif struct_def.field_information.tag == SerializedNativeStructFlag.DECLARED:
            field_count = struct_def.field_information.field_count
            fields = struct_def.field_information.fields
            field_types = []
            for field in module.field_def_range(field_count, fields):
                ty = self.resolve_signature_token(
                    module,
                    module.type_signature_at(field.signature).v0,
                    type_context,
                    data_view,
                )
                # `field_types` is initally empty, a single element is pushed
                # per loop iteration and the number of iterations is bound to
                # the max size of `module.field_def_range()`.
                # MIRAI cannot currently check this bound in terms of
                # `field_count`.
                assert (field_types.__len__() < usize.max_value)
                field_types.append(ty)

            sdef = StructDef.new(field_types)
        else:
            bail("unreachable!")

        # If multiple writers write to def at the same time, the last one will win. It's possible
        # to have multiple copies of a class def floating around, but that probably isn't going
        # to be a big deal.
        module.cache_struct_def(idx, deepcopy(sdef))
        return sdef


    def instantiate_struct_def(
        self,
        module: LoadedModule,
        idx: StructDefinitionIndex,
        type_instantiation: List[Type],
        data_view: InterpreterContext,
    ) -> StructDef:
        struct_def = self.resolve_struct_def(module, idx, data_view)
        type_context = TypeContext(type_instantiation)
        return type_context.subst_struct_def(struct_def)


    # Resolve a ModuleId into a LoadedModule if the module has been cached already.
    #
    # Returns:
    #
    # * `LoadedModule` if such module exists.
    # * `Err(...)` for a verification issue in the module or for a VM invariant violation.
    def get_loaded_module(
        self,
        mid: ModuleId,
        data_view: InterpreterContext,
    ) -> LoadedModule:
        if mid in self.cmap:
            return self.cmap[mid]

        module = load_and_verify_module_id(mid, data_view)
        loaded_module = LoadedModule.new(module)
        self.cmap[deepcopy(mid)] = loaded_module
        return loaded_module


    def cache_module(self, module: VerifiedModule):
        module_id = module.self_id()
        # TODO: Check ModuleId duplication in statedb
        loaded_module = LoadedModule.new(module)
        if module_id not in self.cmap:
            self.cmap[module_id] = loaded_module


    # Resolve a StructHandle into a StructDef recursively in either the cache or the `fetcher`.
    def resolve_struct_handle(
        self,
        module: LoadedModule,
        idx: StructHandleIndex,
        data_view: InterpreterContext,
    ) -> StructDef:
        struct_handle = module.struct_handle_at(idx)
        struct_name = module.identifier_at(struct_handle.name)
        struct_def_module_id = StructHandleView(module, struct_handle).module_id()
        module = self.get_loaded_module(struct_def_module_id, data_view)
        struct_def_idx = module.get_struct_def_index(struct_name)
        return self.resolve_struct_def(module, struct_def_idx, data_view)


    # Resolve a SignatureToken into a Type recursively in either the cache or the `fetcher`.
    def resolve_signature_token(
        self,
        module: LoadedModule,
        tok: SignatureToken,
        type_context: TypeContext,
        data_view: InterpreterContext,
    ) -> Type:
        if tok.tag == SerializedType.BOOL:
            return Type('Bool')
        elif tok.tag == SerializedType.U8:
            return Type('U8')
        elif tok.tag == SerializedType.U64:
            return Type('U64')
        elif tok.tag == SerializedType.U128:
            return Type('U128')
        elif tok.tag == SerializedType.BYTEARRAY:
            return Type('ByteArray')
        elif tok.tag == SerializedType.ADDRESS:
            return Type('Address')
        elif tok.tag == SerializedType.VECTOR:
            sub_tok = tok.vector_type
            inner_ty = self.resolve_signature_token(module, sub_tok, type_context, data_view)
            return Type('Vector', inner_ty)
        elif tok.tag == SerializedType.TYPE_PARAMETER:
            return type_context.get_type(tok.typeParameter)
        elif tok.tag == SerializedType.STRUCT:
            (sh_idx, tys) = tok.struct
            arr = []
            for ty in tys:
                resolved_type = self.resolve_signature_token(module, ty, type_context, data_view)
                arr.append(resolved_type)

            ctx = TypeContext(arr)
            struct_def =\
                ctx.subst_struct_def(self.resolve_struct_handle(module, sh_idx, data_view))
            return Type('Struct', struct_def)
        elif tok.tag == SerializedType.REFERENCE:
            sub_tok = tok.reference
            inner_ty = self.resolve_signature_token(module, sub_tok, type_context, data_view)
            return Type('Reference', inner_ty)
        elif tok.tag == SerializedType.MUTABLE_REFERENCE:
            sub_tok = tok.reference
            inner_ty = self.resolve_signature_token(module, sub_tok, type_context, data_view)
            return Type('MutableReference', inner_ty)



def load_and_verify_module_id(
    mid: ModuleId,
    data_view: InterpreterContext,
) -> VerifiedModule:
    blob = data_view.load_module(mid)
    comp_module = CompiledModule.deserialize(blob)
    return VerifiedModule.new(comp_module)
