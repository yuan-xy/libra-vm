from __future__ import annotations
from mol.compiler.bytecode_source_map.marking import MarkedSourceMapping
from mol.compiler.bytecode_source_map.source_map import ModuleSourceMap
from mol.vm.file_format import CompiledModule, CompiledScript
from typing import List, Optional, Any, Union, Tuple, Mapping
from dataclasses import dataclass, field

# An object that associates source code with compiled bytecode and source map.
@dataclass
class SourceMapping:
    # The source map for the bytecode made w.r.t. to the `source_code`
    source_map: ModuleSourceMap

    # The resulting bytecode from compiling the source map
    bytecode: CompiledModule

    # The source code for the bytecode. This is not required for disassembly, but it is required
    # for being able to print out corresponding source code for marked functions and structs.
    # Unused for now, this will be used when we start printing function/struct markings
    source_code: Optional[Tuple[str, str]] = None

    # Function and class markings. These are used to lift up annotations/messages on the bytecode
    # into the disassembled program and/or IR source code.
    marks: Optional[MarkedSourceMapping] = None

    @classmethod
    def new_from_script(cls,
        source_map: ModuleSourceMap,
        bytecode: CompiledScript,
    ) -> SourceMapping:
        return cls(source_map, bytecode.into_module())


    def with_marks(self, marks: MarkedSourceMapping):
        self.marks = marks


    def with_source_code(self, source_code: Tuple[str, str]):
        self.source_code = source_code
