from bytecode_verifier.verifier import VerifiedModule
from functional_tests.compiler import Compiler, ScriptOrModule
from functional_tests import testsuite
from compiler.ir_to_bytecode.compiler import compile_module, compile_script
from compiler.ir_to_bytecode.parser import parse_script_or_module
from libra.account_address import Address
from libra.rustlib import format_str
from move_ir.types import ast
from stdlib import stdlib_modules
from dataclasses import dataclass
from typing import List, Optional, Callable

@dataclass
class IRCompiler(Compiler):
    deps: List[VerifiedModule]


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
            return ScriptOrModule(script=script, source_map=source_map)

        elif sorm.tag == ast.ScriptOrModule.MODULE:
            parsed_module = sorm.value
            log(format_str("{}", parsed_module))
            module, source_map = compile_module(address, parsed_module, self.deps)
            verified = \
                VerifiedModule.bypass_verifier_DANGEROUS_FOR_TESTING_ONLY(module)
            self.deps.append(verified)
            return ScriptOrModule(module=module, source_map=source_map)


    def stdlib(self) -> Optional[List[VerifiedModule]]:
        return stdlib_modules()


def test_ir_testcase(filepath: str):
    # The IR tests always run with the staged stdlib
    stdlib = stdlib_modules()
    compiler = IRCompiler(stdlib)
    testsuite.functional_tests(compiler, filepath)
