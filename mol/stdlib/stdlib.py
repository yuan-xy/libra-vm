from mol.vm.file_format import CompiledScript, CompiledModule
from mol.bytecode_verifier import VerifiedModule
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname
from typing import List, Mapping
from canoser import Struct

class VecVecU8(Struct):
    _fields = [('modules', [bytes])]

def parse_stdlib_file() -> List[bytes]:
    curdir = dirname(__file__)
    filename = join(curdir, "./staged/stdlib.mv")
    with open(filename, 'rb') as file:
        code = file.read()
        return VecVecU8.deserialize(code).modules

def build_stdlib() -> List[VerifiedModule]:
    modules = parse_stdlib_file()
    cms = [CompiledModule.deserialize(x) for x in modules]
    return [VerifiedModule.new(x) for x in cms]


STAGED_MOVELANG_STDLIB = build_stdlib()

def stdlib_modules()  -> List[VerifiedModule]:
    return STAGED_MOVELANG_STDLIB


def build_stdlib_map() -> Mapping[str, CompiledModule]:
    ret = {}
    modules = parse_stdlib_file()
    cms = [CompiledModule.deserialize(x) for x in modules]
    for v in cms:
        ret[v.name()] = v
    return ret



