from libra.vm_error import StatusCode, VMStatus

from libra_vm.errors import verification_error
from libra_vm.file_format import (
        CompiledModule, FieldDefinitionIndex, FunctionHandleIndex, ModuleHandleIndex,
        StructFieldInformation, StructHandleIndex, TableIndex
    )
from libra_vm import IndexKind, ModuleAccess, SerializedNativeStructFlag
from typing import List, Optional
from libra.rustlib import usize
from dataclasses import dataclass

# This module implements a checker for verifying that each vector in a CompiledModule contains
# distinct values. Successful verification implies that an index in vector can be used to
# uniquely name the entry at that index. Additionally, the checker also verifies the
# following:
# - class and field definitions are consistent
# - the handles in class and function definitions point to IMPLEMENTED_MODULE_INDEX
# - all class and function handles pointing to IMPLEMENTED_MODULE_INDEX have a definition

@dataclass
class DuplicationChecker:
    module: CompiledModule

    def verify(self) -> List[VMStatus]:
        Self = self.__class__
        errors = []

        idx = Self.first_duplicate_element(self.module.identifiers())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.Identifier,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.byte_array_pool())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.ByteArrayPool,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.address_pool())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.AddressPool,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.type_signatures())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.TypeSignature,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.function_signatures())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.FunctionSignature,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.locals_signatures())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.LocalsSignature,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(self.module.module_handles())
        if idx is not None:
            errors.append(verification_error(
                IndexKind.ModuleHandle,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(
                [(x.module, x.name) for x in self.module.struct_handles()]
            )
        if idx is not None:
            errors.append(verification_error(
                IndexKind.StructHandle,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(
                [(x.module, x.name) for x in self.module.function_handles()]
            )
        if idx is not None:
            errors.append(verification_error(
                IndexKind.FunctionHandle,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(
                [x.struct_handle for x in self.module.struct_defs()]
            )
        if idx is not None:
            errors.append(verification_error(
                IndexKind.StructDefinition,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        idx = Self.first_duplicate_element(
                [x.function for x in self.module.function_defs()]
            )
        if idx is not None:
            errors.append(verification_error(
                IndexKind.FunctionDefinition,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))

        for (idx, function_def) in enumerate(self.module.function_defs()):
            acquires = function_def.acquires_global_resources
            if Self.first_duplicate_element(acquires) is not None:
                errors.append(verification_error(
                    IndexKind.FunctionDefinition,
                    idx,
                    StatusCode.DUPLICATE_ACQUIRES_RESOURCE_ANNOTATION_ERROR,
                ))

        idx = Self.first_duplicate_element(
                [(x.struct_, x.name) for x in self.module.field_defs()]
            )
        if idx is not None:
            errors.append(verification_error(
                IndexKind.FieldDefinition,
                idx,
                StatusCode.DUPLICATE_ELEMENT,
            ))


        # Check that:
        # (1) the order of class definitions matches the order of field definitions,
        # (2) each class definition and its field definitions point to the same class handle,
        # (3) there are no unused fields,
        # (4) each class has at least one field. serializing a class with zero fields is problematic
        start_field_index: usize = 0
        idx_opt = None
        for (idx, struct_def) in enumerate(self.module.struct_defs()):
            if struct_def.field_information.tag == SerializedNativeStructFlag.NATIVE:
                continue
            elif struct_def.field_information.tag == SerializedNativeStructFlag.DECLARED:
                field_count = struct_def.field_information.field_count
                fields = struct_def.field_information.fields
            else:
                bail("unreachable!")

            if field_count == 0:
                errors.append(verification_error(
                    IndexKind.StructDefinition,
                    idx,
                    StatusCode.ZERO_SIZED_STRUCT,
                ))

            if FieldDefinitionIndex.new(start_field_index) != fields:
                idx_opt = idx
                break

            next_start_field_index = start_field_index + field_count
            all_fields_match = True
            for i in range(start_field_index, next_start_field_index):
                if struct_def.struct_handle != \
                    self.module.field_def_at(FieldDefinitionIndex.new(i)).struct_:
                    all_fields_match = False
                    break

            if not all_fields_match:
                idx_opt = idx
                break

            start_field_index = next_start_field_index

        if idx_opt is not None:
            errors.append(verification_error(
                IndexKind.StructDefinition,
                idx_opt,
                StatusCode.INCONSISTENT_FIELDS,
            ))


        # Check that each class definition is pointing to module handle with index
        # IMPLEMENTED_MODULE_INDEX.
        idx = None
        for i, x in enumerate(self.module.struct_defs()):
            if self.module.struct_handle_at(x.struct_handle).module\
                != ModuleHandleIndex.new(CompiledModule.IMPLEMENTED_MODULE_INDEX):
                idx = i
                break
        if idx is not None:
            errors.append(verification_error(
                IndexKind.StructDefinition,
                idx,
                StatusCode.INVALID_MODULE_HANDLE,
            ))

        # Check that each function definition is pointing to module handle with index
        # IMPLEMENTED_MODULE_INDEX.
        idx = None
        for i, x in enumerate(self.module.function_defs()):
            if self.module.function_handle_at(x.function).module\
                != ModuleHandleIndex.new(CompiledModule.IMPLEMENTED_MODULE_INDEX):
                idx = i
                break
        if idx is not None:
            errors.append(verification_error(
                IndexKind.FunctionDefinition,
                idx,
                StatusCode.INVALID_MODULE_HANDLE,
            ))

        # Check that each class handle with module handle index IMPLEMENTED_MODULE_INDEX is
        # implemented.
        implemented_struct_handles = {x.struct_handle for x in self.module.struct_defs()}

        idx = None
        for x in  range(self.module.struct_handles().__len__()):
            y = StructHandleIndex.new(x)
            if self.module.struct_handle_at(y).module\
                == ModuleHandleIndex.new(CompiledModule.IMPLEMENTED_MODULE_INDEX)\
                and y not in implemented_struct_handles:
                idx = x
                break
        if idx is not None:
            errors.append(verification_error(
                IndexKind.StructHandle,
                idx,
                StatusCode.UNIMPLEMENTED_HANDLE,
            ))


        # Check that each function handle with module handle index IMPLEMENTED_MODULE_INDEX is
        # implemented.
        implemented_function_handles = {x.function for x in self.module.function_defs()}

        idx = None
        for x in range(self.module.function_handles().__len__()):
            y = FunctionHandleIndex.new(x)
            if self.module.function_handle_at(y).module\
                == ModuleHandleIndex.new(CompiledModule.IMPLEMENTED_MODULE_INDEX)\
                and y not in implemented_function_handles:
                idx = x
                break

        if idx is not None:
            errors.append(verification_error(
                IndexKind.FunctionHandle,
                idx,
                StatusCode.UNIMPLEMENTED_HANDLE,
            ))


        return errors


    def first_duplicate_element(it) -> Optional[usize]:
        uniq = set()
        for (i, x) in enumerate(it):
            if type(x) == bytearray:
                x = bytes(x) #make x hashable
            if x in uniq:
                return i
            else:
                uniq.add(x)
        return None