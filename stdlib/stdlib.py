from libra_vm.file_format import CompiledScript, CompiledModule
from bytecode_verifier import VerifiedModule
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname
from typing import List, Mapping

def build_stdlib() -> List[VerifiedModule]:
    ret = []
    curdir = dirname(__file__)
    sdir = join(curdir, "./modules")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        with open(filename, 'r') as file:
            amap = json.load(file)
            code = bytes(amap['code'])
            obj = CompiledModule.deserialize(code)
            ret.append(VerifiedModule.new(obj))
    return ret


ANNOTATED_STDLIB = build_stdlib()

def stdlib_modules()  -> List[VerifiedModule]:
    return ANNOTATED_STDLIB


def build_stdlib_map() -> Mapping[str, CompiledModule]:
    ret = {}
    curdir = dirname(__file__)
    sdir = join(curdir, "./modules")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        with open(filename, 'r') as file:
            amap = json.load(file)
            code = bytes(amap['code'])
            obj = CompiledModule.deserialize(code)
            ret[filename] = obj
    return ret

