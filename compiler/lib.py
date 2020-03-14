from bytecode_verifier import VerifiedModule
from compiler.bytecode_source_map.source_map import ModuleSourceMap, SourceMap
from compiler.ir_to_bytecode.compiler import compile_module, compile_program
from compiler.ir_to_bytecode.parser import parse_program
from libra.account_address import Address
from libra.transaction import Script, TransactionArgument
from move_ir.types.location import Loc
from stdlib import stdlib_modules
from libra_vm.file_format import CompiledModule, CompiledProgram, CompiledScript
from dataclasses import dataclass
from typing import List, Tuple

# An API for the compiler. Supports setting custom options.
@dataclass
class Compiler:
    # The address used as the sender for the compiler.
    address: Address
    # Skip stdlib dependencies if True.
    skip_stdlib_deps: bool
    # Extra dependencies to compile with.
    extra_deps: List[VerifiedModule]

    # The address to use for stdlib.
    stdlib_address: Address = b'\x00' * 32


    # Compiles into a `CompiledProgram` where the bytecode hasn't been serialized.
    def into_compiled_program(self, file_name: str, code: str) -> CompiledProgram:
        return self.compile_impl(file_name, code)[0]


    def into_compiled_program_and_source_maps(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledProgram, SourceMap]:
        (compiled_program, source_maps, _) = self.compile_impl(file_name, code)
        return (compiled_program, source_maps)


    def into_compiled_program_and_source_maps_deps(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledProgram, SourceMap, List[VerifiedModule]]:
        return self.compile_impl(file_name, code)


    # Compiles into a `CompiledProgram` and also returns the dependencies.
    def into_compiled_program_and_deps(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledProgram, List[VerifiedModule]]:
        (compiled_program, _, deps) = self.compile_impl(file_name, code)
        return (compiled_program, deps)


    # Compiles into a `CompiledScript`.
    def into_script(self, file_name: str, code: str) -> CompiledScript:
        compiled_program = self.compile_impl(file_name, code)[0]
        return compiled_program.script


    # Compiles the script into a serialized form.
    def into_script_blob(self, file_name: str, code: str) -> bytes:
        compiled_program = self.compile_impl(file_name, code)[0]
        return compiled_program.script.serialize()


    # Compiles the module.
    def into_compiled_module(self, file_name: str, code: str) -> CompiledModule:
        return self.compile_mod(file_name, code)[0]


    # Compiles the module into a serialized form.
    def into_module_blob(self, file_name: str, code: str) -> bytes:
        compiled_module = self.compile_mod(file_name, code)[0]
        return compiled_module.serialize()


    # Compiles the code and arguments into a `Script` -- the bytecode is serialized.
    def into_program(
        self,
        file_name: str,
        code: str,
        args: List[TransactionArgument],
    ) -> Script:
        return Script.new(self.into_script_blob(file_name, code), args)


    def compile_impl(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledProgram, SourceMap, List[VerifiedModule]]:
        parsed_program = parse_program(file_name, code)
        deps = self.deps()
        (compiled_program, source_maps) = compile_program(self.address, parsed_program, deps)
        return (compiled_program, source_maps, deps)


    def compile_mod(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledModule, ModuleSourceMap, List[VerifiedModule]]:
        parsed_program = parse_program(file_name, code)
        deps = self.deps()
        modules = parsed_program.modules
        assert_equal(modules.__len__(), 1, "Must have single module")
        module = modules.pop()
        (compiled_module, source_map) = compile_module(self.address, module, deps)
        return (compiled_module, source_map, deps)


    def deps(self) -> List[VerifiedModule]:
        extra_deps = self.extra_deps
        self.extra_deps = []
        if self.skip_stdlib_deps:
            return extra_deps
        else:
            deps = stdlib_modules()
            deps.extend(extra_deps)
            return deps
