from __future__ import annotations
from bytecode_source_map.source_map import ModuleSourceMap
from compiler.ir_to_bytecode.compiler import compile_module
from compiler.ir_to_bytecode.parser import parse_module
from libra.account_address import Address
from vm import ModuleAccess, CompiledModule


def read_to_string(path):
    # curdir = dirname(__file__)
    # path = join(curdir, filename)
    with open(path, 'r') as file:
        return file.read()



def do_compile_module(
    source_path: str,
    address: Address,
    dependencies: List[ModuleAccess],
) -> Tuple[CompiledModule, ModuleSourceMap]:
    source = read_to_string(source_path)
    parsed_module = parse_module(source_path, source)
    return compile_module(address, parsed_module, dependencies)

