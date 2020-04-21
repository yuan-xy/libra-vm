import argparse, sys, os, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from pathlib import Path
from mol.bytecode_verifier import VerifiedModule, VerifiedScript, VerifyException
from mol.bytecode_verifier.verifier import verify_module_dependencies
from mol.compiler.ir_to_bytecode.compiler import compile_module, compile_script
from mol.compiler.ir_to_bytecode.parser import parse_script_or_module
from mol.move_ir.types import ast
from libra import AccessPath, Address
from libra.transaction import Script, Module
from libra.vm_error import VMStatus
from mol.stdlib import stdlib_modules
from mol.vm.file_format import CompiledModule, CompiledScript
from typing import List, Tuple


def get_parser():
    parser = argparse.ArgumentParser(prog='IR Compiler', add_help=True)
    parser.add_argument('-a', "--address", help='Account address used for publishing')
    parser.add_argument("--no-stdlib", action='store_true', default=False, help='Do not automatically compile stdlib dependencies')
    parser.add_argument("--no-verify", action='store_true', default=False, help='Do not automatically run the bytecode verifier')
    parser.add_argument('-l', "--list-dependencies", action='store_true', default=False, help='Instead of compiling the source, emit a dependency list of the compiled source')
    parser.add_argument("--deps", dest='deps_path', help='Path to the list of modules that we want to link with')
    parser.add_argument("--src-map", dest='output_source_maps', action='store_true', default=False)
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
        address = Address.normalize_to_bytes(address)

    source_path = args.source_path[0]
    mvir_extension = ".mvir"
    mv_extension = ".mv"
    source_map_extension = ".mvsm"
    if not source_path.endswith(mvir_extension):
        print("File extension for input source file should be '{mvir_extension}'")
        sys.exit(1)

    source = Path(source_path).read_text()
    sorm = parse_script_or_module(source_path, source)

    if args.list_dependencies:
        dependency_list = sorm.value.get_external_deps()
        dependency_list = [AccessPath.code_access_path(m) for m in dependency_list]
        print(dependency_list)
        return

    if args.deps_path is not None:
        deps = Path(args.deps_path).read_text()
        deps_list = json.load(deps) #TTODO: parse deps: List[bytes]
        deps = [VerifiedModule.new(CompiledModule.deserialize(x)) for x in deps_list]
    elif args.no_stdlib:
        deps = []
    else:
        deps = stdlib_modules()

    if sorm.tag == ast.ScriptOrModule.SCRIPT:
        parsed_script = sorm.value
        compiled_script, source_map = compile_script(address, parsed_script, deps)
        if not args.no_verify:
            verified_script = VerifiedScript.new(compiled_script)
            compiled_sorm = verified_script.into_inner()

    elif sorm.tag == ast.ScriptOrModule.MODULE:
        parsed_module = sorm.value
        compiled_module, source_map = compile_module(address, parsed_module, deps)
        if not args.no_verify:
            verified_module = do_verify_module(compiled_module, deps)
            compiled_sorm = verified_module.into_inner()

    if args.output_source_maps:
        source_map_bytes = source_map.to_json()
        path = Path(source_path).with_suffix(source_map_extension)
        path.write_text(source_map_bytes)

    bytes = compiled_sorm.serialize()
    Path(source_path).with_suffix(mv_extension).write_bytes(bytes)

if __name__ == '__main__':
    main()
