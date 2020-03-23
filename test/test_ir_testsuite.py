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


def ir_testsuite(subdir: str):
    curdir = dirname(__file__)
    path = join(curdir, "../../libra/language/ir-testsuite/tests", subdir)
    for root, dirs, files in os.walk(path):
        for file in files:
            if(file.endswith(".mvir")):
                fullname = join(root, file)
                print(file)
                # if file == "imm_borrow_global.mvir":
                run_testcase(fullname)
                # try:
                #     run_testcase(join(root, file))
                #     print("pass")
                # except Exception:
                #     print("FAIL")


def test_block():
    ir_testsuite('block')

def test_borrow_tests():
    ir_testsuite('borrow_tests')

def test_builtins():
    ir_testsuite('builtins')

def test_commands():
    ir_testsuite('commands')

def test_comments():
    ir_testsuite('comments')

def test_data_types():
    ir_testsuite('data_types')

def test_dereference_tests():
    ir_testsuite('dereference_tests')

def test_discovery():
    ir_testsuite('discovery')

def test_epilogue():
    ir_testsuite('epilogue')

def test_examples():
    ir_testsuite('examples')

def test_expressions():
    ir_testsuite('expressions')

def test_failure():
    ir_testsuite('failure')

def test_function_calls():
    ir_testsuite('function_calls')

def test_gas_schedule():
    ir_testsuite('gas_schedule')

def test_generics():
    ir_testsuite('generics')

def test_genesis():
    ir_testsuite('genesis')

def test_global_ref_count():
    ir_testsuite('global_ref_count')

def test_libra_account():
    ir_testsuite('libra_account')

def test_linker_tests():
    ir_testsuite('linker_tests')

def test_method_decorators():
    ir_testsuite('method_decorators')

def test_module_member_types():
    ir_testsuite('module_member_types')

def test_modules():
    ir_testsuite('modules')

def test_move_getting_started_examples():
    ir_testsuite('move_getting_started_examples')

def test_mutate_tests():
    ir_testsuite('mutate_tests')

def test_mutation():
    ir_testsuite('mutation')

def test_natives():
    ir_testsuite('natives')

def test_offer():
    ir_testsuite('offer')

def test_operators():
    ir_testsuite('operators')

def test_payment_channel():
    ir_testsuite('payment_channel')

def test_payments():
    ir_testsuite('payments')

def test_prologue():
    ir_testsuite('prologue')

def test_prover():
    ir_testsuite('prover')

def test_publish():
    ir_testsuite('publish')

def test_recursion():
    ir_testsuite('recursion')

def test_references():
    ir_testsuite('references')

def test_sorted_linked_list():
    ir_testsuite('sorted_linked_list')

def test_testsuite():
    ir_testsuite('testsuite')

def test_transaction_fee_distribution():
    ir_testsuite('transaction_fee_distribution')

def test_transactions():
    ir_testsuite('transactions')

def test_validator_set():
    ir_testsuite('validator_set')

def test_wallets():
    ir_testsuite('wallets')


