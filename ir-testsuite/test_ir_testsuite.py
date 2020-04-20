from functional_tests import testsuite
from functional_tests.ir_compiler import IRCompiler


def test_ir_testcase(filepath: str):
    compiler = IRCompiler()
    testsuite.functional_tests(compiler, filepath)
