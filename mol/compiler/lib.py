from mol.bytecode_verifier import VerifiedModule
from mol.compiler.bytecode_source_map.source_map import ModuleSourceMap
from mol.compiler.ir_to_bytecode.compiler import compile_module, compile_script
from mol.compiler.ir_to_bytecode.parser import parse_module, parse_script
from libra.account_address import Address
from libra.transaction import Script, TransactionArgument
from mol.move_ir.types.location import Loc
from mol.stdlib import stdlib_modules
from mol.vm.file_format import CompiledModule, CompiledScript
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
    stdlib_address: Address = Address.default()


    def into_compiled_script_and_source_map(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledScript, ModuleSourceMap]:
        (compiled_script, source_map, _) = self.compile_script_(file_name, code)
        return (compiled_script, source_map)


    # Compiles the script into a serialized form.
    def into_script_blob(self, file_name: str, code: str) -> bytes:
        compiled_script = self.compile_script_(file_name, code)[0]
        return compiled_script.serialize()


    # Compiles the module.
    def into_compiled_module(self, file_name: str, code: str) -> CompiledModule:
        return self.compile_mod(file_name, code)[0]


    # Compiles the module into a serialized form.
    def into_module_blob(self, file_name: str, code: str) -> bytes:
        compiled_module = self.compile_mod(file_name, code)[0]
        return compiled_module.serialize()


    def compile_script_(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledScript, ModuleSourceMap, List[VerifiedModule]]:
        parsed_script = parse_script(file_name, code)
        deps = self.deps()
        (compiled_script, source_maps) = compile_script(self.address, parsed_script, deps)
        return (compiled_script, source_maps, deps)


    def compile_mod(
        self,
        file_name: str,
        code: str,
    ) -> Tuple[CompiledModule, ModuleSourceMap, List[VerifiedModule]]:
        module = parse_module(file_name, code)
        deps = self.deps()
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
