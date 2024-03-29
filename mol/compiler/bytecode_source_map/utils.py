# flake8: noqa
from __future__ import annotations
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.compiler.bytecode_source_map.source_map import SourceMap
from mol.move_ir.types.location import Loc
from typing import List, Optional, Any, Union, Tuple, Mapping



Error = Tuple[Loc, str]
Errors = List[Error]

def source_map_from_file(file_path: str) -> SourceMap:
    with open(file_path, 'rb') as f:
        bs = f.read()
        return SourceMap.deserialize(bs)

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


def remap_owned_loc_to_loc(m: SourceMap) -> SourceMap:
    return m #Do nothing in python
