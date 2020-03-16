import argparse, sys, os, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from pathlib import Path
from compiler.bytecode_source_map.source_map import ModuleSourceMap, SourceName
from compiler.bytecode_source_map.mapping import SourceMapping
from compiler.bytecode_source_map.utils import module_source_map_from_file, remap_owned_loc_to_loc, OwnedLoc
from disassembler import Disassembler, DisassemblerOptions
from move_ir.types.location import Spanned
from libra_vm.file_format import CompiledModule, CompiledScript
from typing import List, Tuple


def get_parser():
    parser = argparse.ArgumentParser(prog='Move Bytecode Disassembler', add_help=True, description='Print a human-readable version of Move bytecode (.mv files)')
    parser.add_argument('-s', "--script", dest='is_script', action='store_true', default=False, help='Treat input file as a module (default is to treat file as a program)')
    parser.add_argument("--skip-private", action='store_true', default=False, help='Skip printing of private functions')
    parser.add_argument("--skip-code", action='store_true', default=False, help='Do not print the disassembled bytecodes of each function')
    parser.add_argument("--skip-locals", action='store_true', default=False, help='Do not print locals of each function')
    parser.add_argument("--skip-basic-blocks", action='store_true', default=False, help='Do not print the basic blocks of each function')
    parser.add_argument('-b', '--bytecode', nargs=1, help='The path to the bytecode file')
    return parser


def main():
    parser = get_parser()
    argv = sys.argv[1:]
    if not sys.stdin.isatty():
        argv.extend(sys.stdin.read().strip().split())
    args = parser.parse_args(argv)

    move_extension = ".mvir"
    mv_bytecode_extension = ".mv"
    source_map_extension = ".mvsm"

    bytecode_file_path = args.bytecode[0]

    if not bytecode_file_path.endswith(mv_bytecode_extension):
        print(f"File extension for input file should be '{mv_bytecode_extension}'")
        sys.exit(1)

    bytecode_bytes = Path(bytecode_file_path).read_bytes()

    source_path = Path(bytecode_file_path).with_suffix(move_extension)
    if source_path.exists():
        source = source_path.read_text()
    else:
        source = None

    source_map_path = Path(bytecode_file_path).with_suffix(source_map_extension)
    if source_map_path.exists():
        source_map = module_source_map_from_file(source_map_path)
    else:
        source_map = None

    disassembler_options = DisassemblerOptions()
    disassembler_options.print_code = not args.skip_code
    disassembler_options.only_public = not args.skip_private
    disassembler_options.print_basic_blocks = not args.skip_basic_blocks
    disassembler_options.print_locals = not args.skip_locals

    # TODO: make source mapping work with the move source language
    no_loc = Spanned.unsafe_no_loc(cls=Spanned, value=()).loc
    if args.is_script:
        compiled_script = CompiledScript.deserialize(bytecode_bytes)
        if not source_map:
            source_map = ModuleSourceMap.dummy_from_script(compiled_script, no_loc)
        source_mapping = SourceMapping.new_from_script(source_map, compiled_script)
    else:
        compiled_module = CompiledModule.deserialize(bytecode_bytes)
        if not source_map:
            source_map = ModuleSourceMap.dummy_from_module(compiled_module, no_loc)

        source_mapping = SourceMapping(source_map, compiled_module)

    if source is not None:
        source_mapping.with_source_code((source_path, source))

    disassembler = Disassembler(source_mapping, disassembler_options)
    dissassemble_string = disassembler.disassemble()
    print(dissassemble_string)


if __name__ == '__main__':
    main()
