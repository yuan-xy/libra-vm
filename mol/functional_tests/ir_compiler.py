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


class IRCompiler(Compiler):

    def __init__(self, deps: List[VerifiedModule] = None):
        if deps is None:
            deps = stdlib_modules()
        self.deps = deps


    def compile(
        self,
        log: Callable[[str], None],
        address: Address,
        ins: str,
    ) -> ScriptOrModule:
        sorm = parse_script_or_module("unused_file_name", ins)
        if sorm.tag == ast.ScriptOrModule.SCRIPT:
            parsed_script = sorm.value
            log(format_str("{}", parsed_script))
            script, source_map = compile_script(address, parsed_script, self.deps)
            source_mapping = SourceMapping.new_from_script(source_map, script)
            source_mapping.with_source_code("unused_file_name", ins)
            return ScriptOrModule(script=script, source_map=source_map, source_mapping=source_mapping)

        elif sorm.tag == ast.ScriptOrModule.MODULE:
            parsed_module = sorm.value
            log(format_str("{}", parsed_module))
            module, source_map = compile_module(address, parsed_module, self.deps)
            source_mapping = SourceMapping(source_map, module)
            source_mapping.with_source_code("unused_file_name", ins)
            verified = \
                VerifiedModule.bypass_verifier_DANGEROUS_FOR_TESTING_ONLY(module)
            self.deps.append(verified)
            return ScriptOrModule(module=module, source_map=source_map, source_mapping=source_mapping)


    def stdlib(self) -> Optional[List[VerifiedModule]]:
        return self.deps
