from bytecode_verifier.verifier import VerifiedModule
from functional_tests.compiler import Compiler, ScriptOrModule
from functional_tests import testsuite
from compiler.ir_to_bytecode.compiler import compile_module, compile_script
from compiler.ir_to_bytecode.parser import parse_script_or_module
from libra.account_address import Address
from libra.rustlib import format_str
from move_ir.types import ast
from stdlib import stdlib_modules
import os
from os import listdir
from os.path import isfile, join, abspath, dirname
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
        sorm = parse_script_or_module('<file_path>', ins)
        if sorm.tag == ast.ScriptOrModule.SCRIPT:
            parsed_script = sorm.value
            log(format_str("{}", parsed_script))
            return ScriptOrModule(script=compile_script(address, parsed_script, self.deps)[0])

        elif sorm.tag == ast.ScriptOrModule.MODULE:
            parsed_module = sorm.value
            log(format_str("{}", parsed_module))
            module = compile_module(address, parsed_module, self.deps)[0]
            verified = \
                VerifiedModule.bypass_verifier_DANGEROUS_FOR_TESTING_ONLY(module)
            self.deps.append(verified)
            return ScriptOrModule(module=module)


    def stdlib(self) -> Optional[List[VerifiedModule]]:
        return stdlib_modules()


def run_testcase(path: str):
    # The IR tests always run with the staged stdlib
    stdlib = stdlib_modules()
    compiler = IRCompiler(stdlib)
    testsuite.functional_tests(compiler, path)


def test_ir_testsuite():
    curdir = dirname(__file__)
    path = join(curdir, "../../libra/language/ir-testsuite/tests")
    for root, dirs, files in os.walk(path):
        for file in files:
            if(file.endswith(".mvir")):
                fullname = join(root, file)
                print(file)
                # if file == "return_type_mismatch_and_unused_resource.mvir":
                # run_testcase(fullname)
                try:
                    run_testcase(join(root, file))
                    print("pass")
                except Exception:
                    print("FAIL")

