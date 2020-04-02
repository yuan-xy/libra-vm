"""
/***************************************************************************************
 *
 * Don't edit this file
 *
 *   All code is copied to file_format.py
 *
 **************************************************************************************/

from vm.file_format import (
        AddressPoolIndex, ByteArrayPoolIndex, CompiledModule, CompiledModuleMut, CompiledScript,
        FieldDefinition, FieldDefinitionIndex, FunctionDefinition, FunctionDefinitionIndex,
        FunctionHandle, FunctionHandleIndex, FunctionSignature, FunctionSignatureIndex,
        IdentifierIndex, LocalsSignature, LocalsSignatureIndex, MemberCount, ModuleHandle,
        ModuleHandleIndex, StructDefinition, StructDefinitionIndex, StructHandle,
        StructHandleIndex, TypeSignature, TypeSignatureIndex)
from vm.internals import ModuleIndex
from libra import Address
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus
import abc
from libra.rustlib import ensure, bail, usize
from canoser import Uint8, Uint32, Uint16, Uint64, Uint128
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# Defines accessors for compiled modules.



# Represents accessors for a compiled module.
#
# This is a trait to allow working across different wrappers for `CompiledModule`.
class ModuleAccess(abc.ABC):
    # Returns the `CompiledModule` that will be used for accesses.
    @abc.abstractmethod
    def as_module(self) -> CompiledModule:
        pass

    # Returns the `ModuleHandle` for `self`.
    def self_handle(self) -> ModuleHandle:
        return self.module_handle_at(ModuleHandleIndex(
            CompiledModule.IMPLEMENTED_MODULE_INDEX,
        ))


    # Returns the name of the module.
    def name(self) -> IdentStr:
        return self.identifier_at(self.self_handle().name)


    # Returns the address of the module.
    def address(self) -> Address:
        return self.address_at(self.self_handle().address)


    def module_handle_at(self, idx: ModuleHandleIndex) -> ModuleHandle:
        return self.as_module().as_inner().module_handles[idx.into_index()]


    def struct_handle_at(self, idx: StructHandleIndex) -> StructHandle:
        return self.as_module().as_inner().struct_handles[idx.into_index()]


    def function_handle_at(self, idx: FunctionHandleIndex) -> FunctionHandle:
        return self.as_module().as_inner().function_handles[idx.into_index()]


    def type_signature_at(self, idx: TypeSignatureIndex) -> TypeSignature:
        return self.as_module().as_inner().type_signatures[idx.into_index()]


    def function_signature_at(self, idx: FunctionSignatureIndex) -> FunctionSignature:
        return self.as_module().as_inner().function_signatures[idx.into_index()]


    def locals_signature_at(self, idx: LocalsSignatureIndex) -> LocalsSignature:
        return self.as_module().as_inner().locals_signatures[idx.into_index()]


    def identifier_at(self, idx: IdentifierIndex) -> IdentStr:
        return self.as_module().as_inner().identifiers[idx.into_index()]


    def byte_array_at(self, idx: ByteArrayPoolIndex) -> bytearray:
        return self.as_module().as_inner().byte_array_pool[idx.into_index()]


    def address_at(self, idx: AddressPoolIndex) -> Address:
        return self.as_module().as_inner().address_pool[idx.into_index()]


    def struct_def_at(self, idx: StructDefinitionIndex) -> StructDefinition:
        return self.as_module().as_inner().struct_defs[idx.into_index()]


    def field_def_at(self, idx: FieldDefinitionIndex) -> FieldDefinition:
        return self.as_module().as_inner().field_defs[idx.into_index()]


    def function_def_at(self, idx: FunctionDefinitionIndex) -> FunctionDefinition:
        return self.as_module().as_inner().function_defs[idx.into_index()]


    def get_field_signature(self, field_definition_index: FieldDefinitionIndex) -> TypeSignature:
        field_definition = self.field_def_at(field_definition_index)
        return self.type_signature_at(field_definition.signature)


    # XXX is a partial range required here
    def module_handles(self) -> List[ModuleHandle]:
        return self.as_module().as_inner().module_handles


    def struct_handles(self) -> List[StructHandle]:
        return self.as_module().as_inner().struct_handles


    def function_handles(self) -> List[FunctionHandle]:
        return self.as_module().as_inner().function_handles


    def type_signatures(self) -> List[TypeSignature]:
        return self.as_module().as_inner().type_signatures


    def function_signatures(self) -> List[FunctionSignature]:
        return self.as_module().as_inner().function_signatures


    def locals_signatures(self) -> List[LocalsSignature]:
        return self.as_module().as_inner().locals_signatures


    def byte_array_pool(self) -> List[bytearray]:
        return self.as_module().as_inner().byte_array_pool


    def address_pool(self) -> List[Address]:
        return self.as_module().as_inner().address_pool


    def identifiers(self) -> List[Identifier]:
        return self.as_module().as_inner().identifiers


    def struct_defs(self) -> List[StructDefinition]:
        return self.as_module().as_inner().struct_defs


    def field_defs(self) -> List[FieldDefinition]:
        return self.as_module().as_inner().field_defs


    def function_defs(self) -> List[FunctionDefinition]:
        return self.as_module().as_inner().function_defs


    def module_id_for_handle(self, module_handle_idx: ModuleHandle) -> ModuleId:
        return self.as_module().module_id_for_handle(module_handle_idx)


    def self_id(self) -> ModuleId:
        return self.as_module().self_id()


    def field_def_range(
        self,
        field_count: MemberCount,
        first_field: FieldDefinitionIndex,
    ) -> List[FieldDefinition]:
        first_field = first_field.v0
        field_count = int(field_count)
        # Both `first_field` and `field_count` are `Uint16` before being converted to usize
        assert (first_field <= usize.max_value - field_count)
        last_field = first_field + field_count
        return self.as_module().as_inner().field_defs[first_field:last_field]


    def is_field_in_struct(
        self,
        field_definition_index: FieldDefinitionIndex,
        struct_handle_index: StructHandleIndex,
    ) -> bool:
        field_definition = self.field_def_at(field_definition_index)
        return struct_handle_index == field_definition.struct_



# Represents accessors for a compiled script.
#
# This is a trait to allow working across different wrappers for `CompiledScript`.
class ScriptAccess(abc.ABC):
    # Returns the `CompiledScript` that will be used for accesses.
    @abc.abstractmethod
    def as_script(self) -> CompiledScript:
        pass

    # Returns the `ModuleHandle` for `self`.
    def self_handle(self) -> ModuleHandle:
        return self.module_handle_at(ModuleHandleIndex(
            CompiledModule.IMPLEMENTED_MODULE_INDEX,
        ))


    def module_handle_at(self, idx: ModuleHandleIndex) -> ModuleHandle:
        return self.as_script().as_inner().module_handles[idx.into_index()]


    def struct_handle_at(self, idx: StructHandleIndex) -> StructHandle:
        return self.as_script().as_inner().struct_handles[idx.into_index()]


    def function_handle_at(self, idx: FunctionHandleIndex) -> FunctionHandle:
        return self.as_script().as_inner().function_handles[idx.into_index()]


    def type_signature_at(self, idx: TypeSignatureIndex) -> TypeSignature:
        return self.as_script().as_inner().type_signatures[idx.into_index()]


    def function_signature_at(self, idx: FunctionSignatureIndex) -> FunctionSignature:
        return self.as_script().as_inner().function_signatures[idx.into_index()]


    def locals_signature_at(self, idx: LocalsSignatureIndex) -> LocalsSignature:
        return self.as_script().as_inner().locals_signatures[idx.into_index()]


    def identifier_at(self, idx: IdentifierIndex) -> IdentStr:
        return self.as_script().as_inner().identifiers[idx.into_index()]


    def byte_array_at(self, idx: ByteArrayPoolIndex) -> bytearray:
        return self.as_script().as_inner().byte_array_pool[idx.into_index()]


    def address_at(self, idx: AddressPoolIndex) -> Address:
        return self.as_script().as_inner().address_pool[idx.into_index()]


    def module_handles(self) -> List[ModuleHandle]:
        return self.as_script().as_inner().module_handles


    def struct_handles(self) -> List[StructHandle]:
        return self.as_script().as_inner().struct_handles


    def function_handles(self) -> List[FunctionHandle]:
        return self.as_script().as_inner().function_handles


    def type_signatures(self) -> List[TypeSignature]:
        return self.as_script().as_inner().type_signatures


    def function_signatures(self) -> List[FunctionSignature]:
        return self.as_script().as_inner().function_signatures


    def locals_signatures(self) -> List[LocalsSignature]:
        return self.as_script().as_inner().locals_signatures


    def byte_array_pool(self) -> List[bytearray]:
        return self.as_script().as_inner().byte_array_pool


    def address_pool(self) -> List[Address]:
        return self.as_script().as_inner().address_pool


    def identifiers(self) -> List[Identifier]:
        return self.as_script().as_inner().identifiers


    def main(self) -> FunctionDefinition:
        return self.as_script().as_inner().main

"""
