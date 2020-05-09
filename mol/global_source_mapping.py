from typing import Mapping, Optional
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.compiler.bytecode_source_map.utils import source_map_from_file
from libra import Address
from libra.rustlib import bail
from os.path import join, abspath, dirname
from os import listdir
from pathlib import Path
import re


def camel_to_snake(name):
    if name == "FixedPoint32":
        return "fixedpoint32"
    elif name == "LBR":
        return "lbr"
    elif name == "LibraConfig":
        return "libra_configs"
    elif name == "LibraTimestamp":
        return "libra_time"
    else:
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

def snake_to_camel(word):
    return ''.join(x.capitalize() for x in word.split('_'))


class GlobalSourceMapping:
    mapping: Mapping[str, SourceMapping] = {}

    @classmethod
    def init_std_mapping(cls) -> None:
        address = Address.default().hex()
        curdir = dirname(__file__)
        path = join(curdir, "./stdlib/modules/")
        mvs = [f for f in listdir(path) if f.endswith(".mv")]
        for x in mvs:
            module = x.split(".")[0]
            mv = Path(join(path, x))
            mvsm = mv.with_suffix(".mvsm")
            move = Path(join(path, camel_to_snake(module))).with_suffix(".move")
            if move.exists() and mvsm.exists():
                qual_name = "::".join([address, module])
                source_map = source_map_from_file(mvsm)
                mapping = SourceMapping(source_map, mv.read_bytes())
                mapping.with_source_code(move, move.read_text())
                cls.mapping[qual_name] = mapping
            else:
                bail(f"can't find source or mapping for {mv}")

    @classmethod
    def add(cls, address: str, module: str, mapping: SourceMapping) -> None:
        qual_name = "::".join([address, module])
        cls.add_mapping(qual_name, mapping)

    @classmethod
    def add_mapping(cls, qual_name: str, mapping: SourceMapping) -> None:
        if not cls.mapping:
            cls.init_std_mapping()
        cls.mapping[qual_name] = mapping

    @classmethod
    def find_mapping(cls, qual_name: str) -> Optional[SourceMapping]:
        if qual_name in cls.mapping:
            return cls.mapping[qual_name]
        else:
            return None

    @classmethod
    def find(cls, address: str, module: str) -> Optional[SourceMapping]:
        qual_name = "::".join([address, module])
        return cls.find_mapping(qual_name)



