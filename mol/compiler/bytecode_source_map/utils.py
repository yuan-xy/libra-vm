# flake8: noqa
from __future__ import annotations
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.compiler.bytecode_source_map.source_map import ModuleSourceMap
from mol.move_ir.types.location import Loc
from typing import List, Optional, Any, Union, Tuple, Mapping
from dataclasses import dataclass, field
import json


Error = Tuple[Loc, str]
Errors = List[Error]

def module_source_map_from_file(file_path: str) -> ModuleSourceMap:
    with open(file_path) as f:
        jstr = f.read()
        obj = json.loads(jstr)
        return ModuleSourceMap.from_dict(obj)

def render_errors(source_mapper: SourceMapping, errors: Errors) -> None:
    if source_mapper.source_code is not None:
        (source_file_name, source_string) = source_mapper.source_code
        codemap = Files.new()
        fid = codemap.add(source_file_name, source_string)
        for err in errors:
            diagnostic = create_diagnostic(fid, err)
            writer = StandardStream.stderr(ColorChoice.Auto)
            emit(writer, Config.default(), codemap, diagnostic)
    else:
        raise "Unable to render errors since source file information is not available"


def create_diagnostic(fid: FileId, err: Error) -> Diagnostic:
    (loc, msg) = err
    return Diagnostic.new_error("", BlockLabel.new(fid, loc.span, msg))


#***************************************************************************
# Deserialization helper
#***************************************************************************

class OwnedLoc(Loc):
    pass


def remap_owned_loc_to_loc(m: ModuleSourceMap) -> ModuleSourceMap:
    return m #Do nothing in python
