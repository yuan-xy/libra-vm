from __future__ import annotations
from mol.vm.file_format import(
    CodeOffset, FieldDefinitionIndex, FunctionDefinitionIndex, StructDefinitionIndex, TableIndex
)
from typing import List, Optional, Any, Union, Tuple, Mapping
from dataclasses import dataclass, field
from libra.rustlib import usize

def insert_list_item_in_map(amap, key, value):
    if key in amap:
        amap[key].append(value)
    else:
        amap[key] = [value]

def apply_in_map(amap, key, default, lambd):
    if key in amap:
        value = amap[key]
        lambd(value)
    else:
        amap[key] = default
        lambd(default)

# A data structure used to track any markings or extra information that is desired to be exposed
# in the disassembled function definition. Every marking can have multiple messages associated with it.
@dataclass
class FunctionMarking:
    # Code offset markings
    code_offsets: Mapping[CodeOffset, List[str]] = field(default_factory=dict) #BTreeMap

    # Type parameters markings
    type_param_offsets: Mapping[usize, List[str]] = field(default_factory=dict) #BTreeMap

    def code_offset(self, code_offset: CodeOffset, message: str):
        insert_list_item_in_map(self.code_offsets, code_offset, message)

    def type_param(self, type_param_index: usize, message: str):
        insert_list_item_in_map(self.type_param_offsets, type_param_index, message)


# A data structure used to track any markings or extra information that is desired to be exposed
# in the disassembled class definition. Every marking can have multiple messages associated with it.
@dataclass
class StructMarking:
    # Field markings
    fields: Mapping[FieldDefinitionIndex, List[str]] = field(default_factory=dict) #BTreeMap

    # Type parameter markings
    type_param_offsets: Mapping[usize, List[str]] = field(default_factory=dict) #BTreeMap

    def field(self, field_index: FieldDefinitionIndex, message: str):
        insert_list_item_in_map(self.fields, field_index, message)

    def type_param(self, type_param_index: usize, message: str):
        insert_list_item_in_map(self.type_param_offsets, type_param_index, message)


# A data structure that contains markings for both functions and structs. This will be used for
# printing out error messages and the like.
@dataclass
class MarkedSourceMapping:
    # Any function markings
    function_marks: Mapping[TableIndex, FunctionMarking] = field(default_factory=dict) #BTreeMap

    # Any class marking
    struct_marks: Mapping[TableIndex, StructMarking] = field(default_factory=dict) #BTreeMap

    def mark_code_offset(
        self,
        function_definition_index: FunctionDefinitionIndex,
        code_offset: CodeOffset,
        message: str,
    ):
        apply_in_map(
            self.function_marks,
            function_definition_index.v0,
            FunctionMarking(),
            lambda x: x.code_offset(code_offset, message),
        )


    def mark_function_type_param(
        self,
        function_definition_index: FunctionDefinitionIndex,
        type_param_offset: usize,
        message: str,
    ):
        apply_in_map(
            self.function_marks,
            function_definition_index.v0,
            FunctionMarking(),
            lambda x: x.type_param(type_param_offset, message),
        )


    def mark_struct_field(
        self,
        struct_definition_index: StructDefinitionIndex,
        field_def_index: FieldDefinitionIndex,
        message: str,
    ):
        apply_in_map(
            self.struct_marks,
            struct_definition_index.v0,
            StructMarking(),
            lambda x: x.field(field_def_index, message),
        )


    def mark_struct_type_param(
        self,
        struct_definition_index: StructDefinitionIndex,
        type_param_offset: usize,
        message: str,
    ):
        apply_in_map(
            self.struct_marks,
            struct_definition_index.v0,
            StructMarking(),
            lambda x: x.type_param(type_param_offset, message),
        )
