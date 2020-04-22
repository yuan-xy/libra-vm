from __future__ import annotations
from libra.account_address import Address
from mol.move_core.types.identifier import Identifier
from mol.move_ir.types.ast import ModuleName, NopLabel, QualifiedModuleIdent
from mol.move_ir.types.codespan import Span
from mol.move_ir.types.location import Loc
from mol.vm.file_format import (
        AddressPoolIndex, CodeOffset, CompiledModule, CompiledScript, FieldDefinitionIndex,
        FunctionDefinition, FunctionDefinitionIndex, IdentifierIndex, StructDefinition,
        StructDefinitionIndex, TableIndex,
    )
from mol.vm import ModuleIndex, ModuleAccess, ScriptAccess, VMException
from typing import List, Optional, Any, Union, Tuple, Dict, Callable
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from libra.rustlib import list_get, bail, usize
from copy import deepcopy
from canoser import Uint64
import json
import logging

logger = logging.getLogger(__name__)

CodeOffset = int #Uint16
TableIndex = int #Uint16

Location = Loc
SourceName = Tuple[str, Location]

@dataclass
class CodeLocation(Loc):
    line_no: Optional[int] = None


@dataclass_json
@dataclass
class StructSourceMap:
    # The source declaration location of the struct
    decl_location: Location

    # Important: type parameters need to be added in the order of their declaration
    type_parameters: List[SourceName] = field(default_factory=list)

    # Note that fields to a struct source map need to be added in the order of the fields in the
    # struct definition.
    fields: List[Location] = field(default_factory=list)

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2)

    def add_type_parameter(self, type_name: SourceName):
        self.type_parameters.append(type_name)


    def get_type_parameter_name(
        self,
        type_parameter_idx: usize,
    ) -> Optional[SourceName]:
        return deepcopy(list_get(self.type_parameters,type_parameter_idx))


    def add_field_location(self, field_loc: Location):
        self.fields.append(field_loc)


    def get_field_location(self, field_index: FieldDefinitionIndex) -> Optional[Location]:
        return deepcopy(list_get(self.fields, field_index.into_index()))


    def dummy_struct_map(
        self,
        module: CompiledModule,
        struct_def: StructDefinition,
        default_loc: Location,
    ) -> None:
        struct_handle = module.struct_handle_at(struct_def.struct_handle)

        # Add dummy locations for the fields
        try:
            count = struct_def.declared_field_count()
            for _x in range(count):
                self.fields.append(default_loc)
        except VMException as err:
            logger.info(err)

        for i in range(struct_handle.type_formals.__len__()):
            name = f"Ty{i}"
            self.add_type_parameter((name, deepcopy(default_loc)))


    def remap_locations(
        self,
        f: Callable[[Any], Any],
    ) -> StructSourceMap:
        decl_location = f(self.decl_location)
        type_parameters = [remap_locations_source_name(n, f) for n in self.type_parameters]
        fields = [f(loc) for loc in self.fields]
        return StructSourceMap(
            decl_location,
            type_parameters,
            fields,
        )

@dataclass_json
@dataclass
class FunctionSourceMap:
    # The source location for the definition of this entire function. Note that in certain
    # instances this will have no valid source location e.g. the "main" function for modules that
    # are treated as programs are synthesized and therefore have no valid source location.
    decl_location: Location

    # Note that type parameters need to be added in the order of their declaration
    type_parameters: List[SourceName] = field(default_factory=list)

    # The index into the vector is the locls index. The corresponding `(Identifier, Location)` tuple
    # is the name and location of the local.
    locls: List[SourceName] = field(default_factory=list)

    # A map to the code offset for a corresponding nop. Nop's are used as markers for some
    # high level language information
    nops: Dict[NopLabel, CodeOffset] = field(default_factory=dict)

    # The source location map for the function body.
    code_map: Dict[CodeOffset, CodeLocation] = field(default_factory=dict)

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2)

    def add_type_parameter(self, type_name: SourceName):
        self.type_parameters.append(type_name)


    def get_type_parameter_name(
        self,
        type_parameter_idx: usize,
    ) -> Optional[SourceName]:
        return deepcopy(list_get(self.type_parameters,type_parameter_idx))


    # A single source-level instruction may possibly map to a number of bytecode instructions. In
    # order to not store a location for each instruction, we instead use a BTreeMap to represent
    # a segment map (holding the left-hand-sides of each segment).  Thus, an instruction
    # sequence is always marked from its starting point. To determine what part of the source
    # code corresponds to a given `CodeOffset` we query to find the element that is the largest
    # number less than or equal to the query. This will give us the location for that bytecode
    # range.
    def add_code_mapping(self, start_offset: CodeOffset, location: Location):
        possible_segment = self.get_code_location(start_offset)
        if possible_segment is None or possible_segment != location:
            self.code_map[start_offset] = location

    # Record the code offset for an Nop label
    def add_nop_mapping(self, label: NopLabel, offset: CodeOffset):
        assert label not in self.nops
        self.nops[label] = offset

    # Not that it is important that locations be added in order.
    def add_local_mapping(self, name: SourceName):
        self.locls.append(name)


    # Recall that we are using a segment tree. We therefore lookup the location for the code
    # offset by performing a range query for the largest number less than or equal to the code
    # offset passed in.
    def get_code_location(self, code_offset: CodeOffset) -> Optional[Location]:
        matched = None
        for k, v in sorted(self.code_map.items()):
            if k <= code_offset:
                matched = v
            else:
                break
        return matched


    def get_local_name(self, local_index: Uint64) -> Optional[SourceName]:
        if local_index<0 or local_index> len(self.locls):
            return None
        ret: SourceName = list_get(self.locls, local_index)
        return ret


    def dummy_function_map(
        self,
        module: CompiledModule,
        function_def: FunctionDefinition,
        default_loc: Location,
    ) -> None:
        function_handle = module.function_handle_at(function_def.function)
        function_signature = module.function_signature_at(function_handle.signature)
        function_code = function_def.code

        # Generate names for each type parameter
        for i in range(function_signature.type_formals.__len__()):
            name = f"Ty{i}"
            self.add_type_parameter((name, deepcopy(default_loc)))

        # Generate names for each local of the function
        if not function_def.is_native():
            locls = module.locals_signature_at(function_code.locals)
            for i in range(locls.v0.__len__()):
                name = f"loc{i}"
                self.add_local_mapping((name, deepcopy(default_loc)))

        # We just need to insert the code map at the 0'th index since we represent this with a
        # segment map
        self.add_code_mapping(0, default_loc)


    def remap_locations(
        self,
        f: Callable[[Any], Any],
    ) -> FunctionSourceMap:
        decl_location = f(self.decl_location)
        type_parameters = [remap_locations_source_name(n, f) for n in self.type_parameters]
        locls = [remap_locations_source_name(n, f) for n in self.locls]
        code_map = {}
        for (i, loc) in self.code_map.items():
            code_map[i] = f(loc)

        return FunctionSourceMap(
            decl_location,
            type_parameters,
            locls,
            code_map,
        )

@dataclass_json
@dataclass
class SourceMap:
    # The name <address.module_name> for module that this source map is for
    module_name: Tuple[Address, Identifier]

    # A mapping of StructDefinitionIndex to source map for each struct/resource
    struct_map: Dict[TableIndex, StructSourceMap]

    # A mapping of FunctionDefinitionIndex to the soure map for that function.
    function_map: Dict[TableIndex, FunctionSourceMap]

    dummy: Optional[bool] = False

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def new(cls, module_name: QualifiedModuleIdent, dummy= False) -> SourceMap:
        ident = module_name.name
        return cls((module_name.address.hex(), ident), {}, {}, dummy)


    def add_top_level_function_mapping(
        self,
        fdef_idx: FunctionDefinitionIndex,
        location: Location,
    ) -> None:
        if fdef_idx.v0 in self.function_map:
            bail("Multiple functions at same function definition index encountered when constructing source map")
        self.function_map[fdef_idx.v0] = FunctionSourceMap(location)


    def add_function_type_parameter_mapping(
        self,
        fdef_idx: FunctionDefinitionIndex,
        name: SourceName,
    ) -> None:
        if fdef_idx.v0 not in self.function_map:
            bail("Tried to add function type parameter mapping to undefined function index")

        func_entry = self.function_map[fdef_idx.v0]
        func_entry.add_type_parameter(name)


    def get_function_type_parameter_name(
        self,
        fdef_idx: FunctionDefinitionIndex,
        type_parameter_idx: usize,
    ) -> SourceName:
        if fdef_idx.v0 not in self.function_map:
            bail("Unable to get function type parameter name")
        return self.function_map[fdef_idx.v0].get_type_parameter_name(type_parameter_idx)



    def add_code_mapping(
        self,
        fdef_idx: FunctionDefinitionIndex,
        start_offset: CodeOffset,
        location: Location,
    ) -> None:
        if fdef_idx.v0 not in self.function_map:
            bail("Tried to add code mapping to undefined function index")

        func_entry = self.function_map[fdef_idx.v0]
        func_entry.add_code_mapping(start_offset, location)


    def add_nop_mapping(
        self,
        fdef_idx: FunctionDefinitionIndex,
        label: NopLabel,
        start_offset: CodeOffset,
    ) -> None:
        func_entry = self.function_map[fdef_idx.v0]
        func_entry.add_nop_mapping(label, start_offset)


    # Given a function definition and a code offset within that function definition, this returns
    # the location in the source code associated with the instruction at that offset.
    def get_code_location(
        self,
        fdef_idx: FunctionDefinitionIndex,
        offset: CodeOffset,
    ) -> Location:
        if fdef_idx.v0 not in self.function_map:
            bail("Tried to get code location from undefined function index")
        return self.function_map[fdef_idx.v0].get_code_location(offset)


    def add_local_mapping(
        self,
        fdef_idx: FunctionDefinitionIndex,
        name: SourceName,
    ) -> None:
        if fdef_idx.v0 not in self.function_map:
            bail("Tried to add local mapping to undefined function index")

        func_entry = self.function_map[fdef_idx.v0]
        func_entry.add_local_mapping(name)


    def get_local_name(
        self,
        fdef_idx: FunctionDefinitionIndex,
        index: Uint64,
    ) -> SourceName:
        if fdef_idx.v0 not in self.function_map:
            bail("Tried to get local name at undefined function index")
        return self.function_map[fdef_idx.v0].get_local_name(index)


    def add_top_level_struct_mapping(
        self,
        struct_def_idx: StructDefinitionIndex,
        location: Location,
    ) -> None:
        if struct_def_idx.v0 in self.struct_map:
            bail("Multiple structs at same struct definition index encountered when constructing source map")

        self.struct_map[struct_def_idx.v0] = StructSourceMap(location)


    def add_struct_field_mapping(
        self,
        struct_def_idx: StructDefinitionIndex,
        location: Location,
    ) -> None:
        if struct_def_idx.v0 not in self.struct_map:
            bail("Tried to add file mapping to undefined struct index")

        struct_entry = self.struct_map[struct_def_idx.v0]
        struct_entry.add_field_location(location)


    def get_struct_field_name(
        self,
        struct_def_idx: StructDefinitionIndex,
        field_idx: FieldDefinitionIndex,
    ) -> Optional[Location]:
        if struct_def_idx.v0 not in self.struct_map:
            bail("Tried to add file mapping to undefined struct index")

        return self.struct_map[struct_def_idx.v0].get_field_location(field_idx)



    def add_struct_type_parameter_mapping(
        self,
        struct_def_idx: StructDefinitionIndex,
        name: SourceName,
    ) -> None:
        if struct_def_idx.v0 not in self.struct_map:
            bail("Tried to add type_parameters to undefined struct index")

        struct_entry = self.struct_map[struct_def_idx.v0]
        struct_entry.add_type_parameter(name)


    def get_struct_type_parameter_name(
        self,
        struct_def_idx: StructDefinitionIndex,
        type_parameter_idx: usize,
    ) -> SourceName:
        if struct_def_idx.v0 not in self.struct_map:
            bail("Unable to get function type parameter name")

        return self.struct_map[struct_def_idx.v0].get_type_parameter_name(type_parameter_idx)


    def get_function_source_map(
        self,
        fdef_idx: FunctionDefinitionIndex,
    ) -> FunctionSourceMap:
        return self.function_map[fdef_idx.v0]


    def get_struct_source_map(
        self,
        struct_def_idx: StructDefinitionIndex,
    ) -> StructSourceMap:
        return self.struct_map[struct_def_idx.v0]


    # Create a 'dummy' source map for a compiled module. This is useful for e.g. disassembling
    # with generated or real names depending upon if the source map is available or not.
    @classmethod
    def dummy_from_module(cls, module: CompiledModule, default_loc: Location) -> SourceMap:
        module_name = module.identifier_at(IdentifierIndex.new(0))
        module_ident =\
            QualifiedModuleIdent(module_name, module.address_at(AddressPoolIndex.new(0)))

        empty_source_map = cls.new(module_ident, dummy= True)

        for (function_idx, function_def) in enumerate(module.function_defs()):
            empty_source_map.add_top_level_function_mapping(
                FunctionDefinitionIndex(function_idx),
                deepcopy(default_loc),
            )
            entry = empty_source_map.function_map[function_idx]
            entry.dummy_function_map(module, function_def, deepcopy(default_loc))

        for (struct_idx, struct_def) in enumerate(module.struct_defs()):
            empty_source_map.add_top_level_struct_mapping(
                StructDefinitionIndex(struct_idx),
                deepcopy(default_loc),
            )
            entry = empty_source_map.struct_map[struct_idx]
            entry.dummy_struct_map(module, struct_def, deepcopy(default_loc))

        return empty_source_map

    @classmethod
    def dummy_from_script(cls, script: CompiledScript, default_loc: Location) -> SourceMap:
        return cls.dummy_from_module(script.into_module(), default_loc)


    def remap_locations(
        self,
        f: Callable[[Any], Any],
    ) -> SourceMap:
        struct_map = {n: m.remap_locations(f) for (n,m) in self.struct_map.items()}
        function_map = {n: m.remap_locations(f) for (n,m) in self.function_map.items()}

        return SourceMap(
            self.module_name,
            struct_map,
            function_map,
        )


def remap_locations_source_name(
    sname: SourceName,
    f: Callable[[Any], Any],
) -> SourceName:
    (aid, loc) = sname
    return (aid, f(loc))


def remap_locations_source_map(
    alist: List[SourceMap],
    f: Callable[[Any], Any],
) -> List[SourceMap]:
    return [m.remap_locations(f) for m in alist]
