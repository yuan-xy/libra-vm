from __future__ import annotations
from bytecode_verifier import VerifiedModule, VerifiedScript
from compiler.ir_to_bytecode.compiler import compile_module, compile_program
from compiler.ir_to_bytecode.parser import parse_module, parse_program

from libra.account_address import Address
from libra.vm_error import VMStatus
from stdlib import stdlib_modules#, StdLibOptions
from libra_vm.file_format import CompiledModule, CompiledScript, ScriptAccess
from libra.rustlib import *



def instr_count(compiled, instr_tag):
    return [x.tag for x in compiled.main().code.code].count(instr_tag)


def compile_script_string_impl(
    code: str,
    deps: List[CompiledModule],
) -> CompiledScript:
    parsed_program = parse_program("file_name", code)
    compiled_program = compile_program(Address.default(), parsed_program, deps)[0]

    serialized_script = compiled_program.script.serialize()
    deserialized_script = CompiledScript.deserialize(serialized_script)
    assert_equal(compiled_program.script, deserialized_script)

    # Always return a CompiledScript because some callers explicitly care about unverified
    # modules.
    return VerifiedScript.new(compiled_program.script).into_inner()


def compile_script_string_and_assert_no_error(
    code: str,
    deps: List[CompiledModule],
) -> CompiledScript:
    return compile_script_string_impl(code, deps)



def compile_script_string(code: str) -> CompiledScript:
    return compile_script_string_and_assert_no_error(code, [])


def compile_script_string_with_deps(
    code: str,
    deps: List[CompiledModule],
) -> CompiledScript:
    return compile_script_string_and_assert_no_error(code, deps)


def compile_script_string_and_assert_error(
    code: str,
    deps: List[CompiledModule],
) -> CompiledScript:
    try:
        compile_script_string_impl(code, deps)
        bail("should raise VerifyException")
    except VerifyException as err:
        return err.data


def compile_module_string_impl(
    code: str,
    deps: List[CompiledModule],
) -> CompiledModule:
    address = Address.default()
    module = parse_module("file_name", code)
    compiled_module = compile_module(address, module, deps)[0]

    serialized_module = compiled_module.serialize()
    deserialized_module = CompiledModule.deserialize(serialized_module)
    assert_equal(compiled_module, deserialized_module)

    # Always return a CompiledModule because some callers explicitly care about unverified
    # modules.
    return VerifiedModule.new(compiled_module).into_inner()


def compile_module_string_and_assert_no_error(
    code: str,
    deps: List[CompiledModule],
) -> CompiledModule:
    return compile_module_string_impl(code, deps)


def compile_module_string(code: str) -> CompiledModule:
    return compile_module_string_and_assert_no_error(code, [])


def compile_module_string_with_deps(
    code: str,
    deps: List[CompiledModule],
) -> CompiledModule:
    return compile_module_string_and_assert_no_error(code, deps)


def compile_module_string_and_assert_error(
    code: str,
    deps: List[CompiledModule],
) -> CompiledModule:
    try:
        compile_module_string_impl(code, deps)
        bail("should raise VerifyException")
    except VerifyException as err:
        return err.data


def count_locals(script: CompiledScript) -> usize:
    return script.locals_signature_at(script.main().code.locals).v0.__len__()


def compile_module_string_with_stdlib(code: str) -> CompiledModule:
    return compile_module_string_and_assert_no_error(code, stdlib())


def compile_script_string_with_stdlib(code: str) -> CompiledScript:
    return compile_script_string_and_assert_no_error(code, stdlib())


def stdlib() -> List[CompiledModule]:
    return [m.into_inner() for m in stdlib_modules()]
