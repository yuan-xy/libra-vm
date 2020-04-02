from .testutils import compile_module_string
from vm.file_format import *
from vm import Opcodes, ScriptAccess
import pytest



def test_compile_script_with_functions():
    code = """
        module Foobar {
            resource FooCoin { value: u64 }

            public value(this: &Self.FooCoin): u64 {
                let value_ref: &u64;
                value_ref = &move(this).value;
                return *move(value_ref);
            }

            public deposit(this: &mut Self.FooCoin, check: Self.FooCoin) {
                let value_ref: &mut u64;
                let value: u64;
                let check_ref: &Self.FooCoin;
                let check_value: u64;
                let new_value: u64;
                let i: u64;
                value_ref = &mut move(this).value;
                value = *copy(value_ref);
                check_ref = &check;
                check_value = Self.value(move(check_ref));
                new_value = copy(value) + copy(check_value);
                *move(value_ref) = move(new_value);
                FooCoin { value: i } = move(check);
                return;
            }
        }

    """
    compiled_module_res = compile_module_string(code)
    assert(compiled_module_res)


def generate_function(name: str, num_formals: usize, num_locals: usize) -> str:
    code = f"public {name}("

    # code.reserve(30 * (num_formals + num_locals))

    for i in range(num_formals):
        code += f"formal_{i}: u64"
        if i < num_formals - 1:
            code += ", "

    code += ") {\n"

    for i in range(num_locals):
        code += f"let x_{i}: u64;\n"

    for i in range(num_locals):
        code += f"x_{i} = {i};\n"


    code += "return;"
    code += "}"
    return code



def test_compile_script_with_large_frame():
    code = """
        module Foobar {
            resource FooCoin { value: u64 }
    """

    # Max number of locals (formals + local variables) is Uint8.max_value().
    code += generate_function("foo_func", 128, 127)

    code += "}"

    compiled_module_res = compile_module_string(code)
    assert(compiled_module_res)



def test_compile_script_with_invalid_large_frame():
    code = """
        module Foobar {
            resource FooCoin { value: u64 }
    """

    # Max number of locals (formals + local variables) is Uint8.max_value().
    code += generate_function("foo_func", 128, 128)

    code += "}"

    with pytest.raises(Exception) as excinfo:
        compiled_module_res = compile_module_string(code)

    assert excinfo.value.__str__() == 'Max number of locals reached'

