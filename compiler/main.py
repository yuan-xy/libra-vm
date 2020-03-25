import argparse, sys, os, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from pathlib import Path
from bytecode_verifier import VerifiedModule, VerifiedScript, VerifyException
from bytecode_verifier.verifier import verify_module_dependencies, VerifiedProgram
# from compiler.bytecode_source_map.source_map import ModuleSourceMap
from compiler.lib import Compiler
from compiler import util
from compiler.ir_to_bytecode.parser import parse_module, parse_script
from libra import AccessPath, Address
from libra.transaction import Script, Module
from libra.vm_error import VMStatus
from stdlib import stdlib_modules
from libra_vm.file_format import CompiledModule #, CompiledProgram, CompiledScript
from typing import List, Tuple


def get_parser():
    parser = argparse.ArgumentParser(prog='IR Compiler', add_help=True)
    parser.add_argument('-m', "--module", dest='module_input', action='store_true', default=False, help='Treat input file as a module (default is to treat file as a program)')
    parser.add_argument('-a', "--address", help='Account address used for publishing')
    parser.add_argument("--no-stdlib", action='store_true', default=False, help='Do not automatically compile stdlib dependencies')
    parser.add_argument("--no-verify", action='store_true', default=False, help='Do not automatically run the bytecode verifier')
    parser.add_argument('-l', "--list-dependencies", action='store_true', default=False, help='Instead of compiling the source, emit a dependency list of the compiled source')
    parser.add_argument("--deps", dest='deps_path', help='Path to the list of modules that we want to link with')
    parser.add_argument("--src-map", dest='output_source_maps', action='store_true', default=False)
    parser.add_argument("--json", action='store_true', default=False, help='bytecode file format is json(default is binary)')
    parser.add_argument('source_path', nargs=1, help='Path to the Move IR source to compile')
    return parser


def print_errors_and_exit(verification_errors: List[VMStatus]):
    print("Verification failed. Errors below:")
    for e in verification_errors:
        print(e)
    sys.exit(1)


def do_verify_module(module: CompiledModule, deps: List[VerifiedModule]) -> VerifiedModule:
    try:
        verified_module = VerifiedModule.new(module)
    except VerifyException as err:
        print_errors_and_exit(err.vm_status)
    errors = verify_module_dependencies(verified_module, deps)
    if errors:
        print_errors_and_exit(errors)

    return verified_module


def main():
    parser = get_parser()
    argv = sys.argv[1:]
    if not sys.stdin.isatty():
        argv.extend(sys.stdin.read().strip().split())
    args = parser.parse_args(argv)


    address = args.address
    if not address:
        address = Address.default()
    else:
        address = bytes.fromhex(address)

    source_path = args.source_path[0]
    mvir_extension = ".mvir"
    mv_extension = ".mv"
    source_map_extension = ".mvsm"
    if not source_path.endswith(mvir_extension):
        print("File extension for input source file should be '{mvir_extension}'")
        sys.exit(1)

    file_name = args.source_path[0]

    if args.list_dependencies:
        source = util.read_to_string(source_path)
        if args.module_input:
            module = parse_module(file_name, source)
            dependency_list = module.get_external_deps()
        else:
            script = parse_script(file_name, source)
            dependency_list = script.get_external_deps()

        dependency_list = [AccessPath.code_access_path(m) for m in dependency_list]
        print(dependency_list)
        return

    if args.deps_path is not None:
        deps = util.read_to_string(args.deps_path)
        deps_list: List[bytes] = json.load(deps) #TTODO: parse deps
        deps = [VerifiedModule.new(CompiledModule.deserialize(x)) for x in deps_list]
    elif args.no_stdlib:
        deps = []
    else:
        deps = stdlib_modules()

    if not args.module_input:
        source = util.read_to_string(source_path)
        compiler = Compiler(
            address,
            args.no_stdlib,
            deps,
        )
        (compiled_program, source_map, dependencies) = compiler\
            .into_compiled_program_and_source_maps_deps(file_name, source)

        if not args.no_verify:
            verified_program = VerifiedProgram.new(compiled_program, dependencies)
            compiled_program = verified_program.into_inner()

        if args.output_source_maps:
            source_map_bytes = source_map[0].to_json()
            path = Path(source_path).with_suffix(source_map_extension)
            path.write_text(source_map_bytes)

        script = compiled_program.script.serialize()
        if args.json:
            payload = Script(script, [])
            Path(source_path).with_suffix(mv_extension).write_text(payload.to_json())
        else:
            Path(source_path).with_suffix(mv_extension).write_bytes(script)
    else:
        (compiled_module, source_map) =\
            util.do_compile_module(source_path, address, deps)
        if not args.no_verify:
            verified_module = do_verify_module(compiled_module, deps)
            compiled_module = verified_module.into_inner()

        if args.output_source_maps:
            source_map_bytes = source_map.to_json()
            Path(source_path).with_suffix(source_map_extension).write_text(source_map_bytes)

        module = compiled_module.serialize()
        if args.json:
            payload = Module(module)
            Path(source_path).with_suffix(mv_extension).write_text(payload.to_json())
        else:
            Path(source_path).with_suffix(mv_extension).write_bytes(module)


if __name__ == '__main__':
    main()
