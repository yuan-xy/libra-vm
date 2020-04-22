from __future__ import annotations
from mol.compiler.bytecode_source_map.marking import MarkedSourceMapping
from mol.compiler.bytecode_source_map.source_map import SourceMap
from mol.move_core import JsonPrintable
from mol.move_ir.types.codespan import Span
from mol.vm.file_format import CompiledModule, CompiledScript
from typing import List, Optional, Any, Union, Tuple, Mapping
from dataclasses import dataclass, field


@dataclass
class SourceCode(JsonPrintable):
    path: str
    lines: List[str]
    begins: List[int]

    def find_line_no(self, span: Span) -> int:
        for i, x in enumerate(self.begins):
            if x > span.end:
                # curline is next line of span, so real lineno is i-1
                # but human readable lineo is starts from 1, so return (i-1)+1 == i
                return i

    @classmethod
    def new(cls, source_path: str, source: str) -> SourceCode:
        begins = [0]
        length = len(source)
        new_line = False
        for i, ch in enumerate(source):
            if new_line:
                begins.append(i)
                new_line = False

            if ch == '\r':
                if i + 1 < length and source[i+1] == '\n':
                    continue
                new_line = True
            elif ch == '\n':
                new_line = True
            else:
                continue

        lines = source.splitlines()
        assert len(lines) == len(begins)
        return cls(source_path, lines, begins)


# An object that associates source code with compiled bytecode and source map.
@dataclass
class SourceMapping(JsonPrintable):
    # The source map for the bytecode made w.r.t. to the `source_code`
    source_map: SourceMap

    # The resulting bytecode from compiling the source map
    bytecode: CompiledModule

    # The source code for the bytecode. This is not required for disassembly, but it is required
    # for being able to print out corresponding source code for marked functions and structs.
    # Unused for now, this will be used when we start printing function/struct markings
    source_code: Optional[SourceCode] = None

    # Function and struct markings. These are used to lift up annotations/messages on the bytecode
    # into the disassembled program and/or IR source code.
    marks: Optional[MarkedSourceMapping] = None

    def has_source_code_and_map(self):
        return self.source_code is not None and not self.source_map.dummy

    @classmethod
    def new_from_script(cls,
        source_map: SourceMap,
        bytecode: CompiledScript,
    ) -> SourceMapping:
        return cls(source_map, bytecode.into_module())


    def with_marks(self, marks: MarkedSourceMapping):
        self.marks = marks


    def with_source_code(self, source_path: str, source: str):
        source_code = SourceCode.new(source_path, source)
        self.source_code = source_code
        if self.source_map.dummy:
            return
        for k, v in self.source_map.function_map.items():
            for kk, vv in v.code_map.items():
                line_no = source_code.find_line_no(vv.span)
                vv.line_no = line_no

