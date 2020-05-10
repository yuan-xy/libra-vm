from mol.bytecode_verifier.verifier import VerifiedModule
from mol.functional_tests.compiler import Compiler, ScriptOrModule
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.compiler.ir_to_bytecode.compiler import compile_module, compile_script
from mol.compiler.ir_to_bytecode.parser import parse_script_or_module
from libra.account_address import Address
from libra.rustlib import format_str
from mol.move_ir.types import ast
from mol.stdlib import stdlib_modules
from typing import List, Optional, Callable
from pathlib import Path


class IRCompiler(Compiler):

    def __init__(self, deps: List[VerifiedModule] = None):
        if deps is None:
            deps = stdlib_modules()
        self.deps = deps
        self.output_source_maps = False

    def write_sourcemap(self, path, source_map, source):
        if self.output_source_maps:
            mapping = SourceMapping(source_map, None)
            mapping.with_source_code(path, source)
            source_map_bytes = source_map.serialize()
            path = Path(path).with_suffix(".mvsm")
            path.write_bytes(source_map_bytes)


    def compile(
        self,
        log: Callable[[str], None],
        address: Address,
        ins: str,
        path: str = None,
    ) -> ScriptOrModule:
        if not self.output_source_maps:
            # don't use real path to compile, otherwise the output will contain source_mapping text
            # which will cause the testcases failed, such as "break_outside_loop.mvir"
            path = "unused_file_name"
        sorm = parse_script_or_module(path, ins)

        if sorm.tag == ast.ScriptOrModule.SCRIPT:
            parsed_script = sorm.value
            log(format_str("{}", parsed_script))
            script, source_map = compile_script(address, parsed_script, self.deps)
            self.write_sourcemap(path, source_map, ins)

            if self.output_source_maps:
                source_mapping = SourceMapping.new_from_script(source_map, script)
                source_mapping.with_source_code(path, ins)
            else:
                source_mapping = None
            return ScriptOrModule(script=script, source_map=source_map, source_mapping=source_mapping)

        elif sorm.tag == ast.ScriptOrModule.MODULE:
            parsed_module = sorm.value
            log(format_str("{}", parsed_module))
            module, source_map = compile_module(address, parsed_module, self.deps)
            self.write_sourcemap(path, source_map, ins)

            if self.output_source_maps:
                source_mapping = SourceMapping(source_map, module)
                source_mapping.with_source_code(path, ins)
            else:
                source_mapping = None

            verified = \
                VerifiedModule.bypass_verifier_DANGEROUS_FOR_TESTING_ONLY(module)
            self.deps.append(verified)
            return ScriptOrModule(module=module, source_map=source_map, source_mapping=source_mapping)


    def stdlib(self) -> Optional[List[VerifiedModule]]:
        return self.deps
