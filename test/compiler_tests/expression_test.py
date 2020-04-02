from __future__ import annotations
from .testutils import *
from vm.file_format import *
from vm import Opcodes
import pytest


def test_compile_script_expr_addition():
    code = """
        main() {
            let x: u64;
            let y: u64;
            let z: u64;
            x = 3;
            y = 5;
            z = move(x) + move(y);
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert_equal(compiled_script.main().code.max_stack_size, 2)
    assert_equal(count_locals(compiled_script), 3)
    assert_equal(compiled_script.main().code.code.__len__(), 9)
    assert(compiled_script.struct_handles().__len__() == 0)
    assert_equal(compiled_script.function_handles().__len__(), 1)
    assert(compiled_script.type_signatures().__len__() == 0)
    assert_equal(compiled_script.function_signatures().__len__(), 1); # method sig
    assert_equal(compiled_script.locals_signatures().__len__(), 1); # local variables sig
    assert_equal(compiled_script.module_handles().__len__(), 1); # the <SELF> module
    assert_equal(compiled_script.identifiers().__len__(), 2); # the name of `main()` + the name of the "<SELF>" module
    assert_equal(compiled_script.address_pool().__len__(), 1); # the empty address of <SELF> module



def test_compile_script_expr_combined():
    code = """
        main() {
            let x: u64;
            let y: u64;
            let z: u64;
            x = 3;
            y = 5;
            z = move(x) + copy(y) * 5 - copy(y);
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert_equal(compiled_script.main().code.max_stack_size, 3)
    assert_equal(count_locals(compiled_script), 3)
    assert_equal(compiled_script.main().code.code.__len__(), 13)
    assert(compiled_script.struct_handles().__len__() == 0)
    assert_equal(compiled_script.function_handles().__len__(), 1)
    assert(compiled_script.type_signatures().__len__() == 0)
    assert_equal(compiled_script.function_signatures().__len__(), 1); # method sig
    assert_equal(compiled_script.locals_signatures().__len__(), 1); # local variables sig
    assert_equal(compiled_script.module_handles().__len__(), 1); # the <SELF> module
    assert_equal(compiled_script.identifiers().__len__(), 2); # the name of `main()` + the name of the "<SELF>" module
    assert_equal(compiled_script.address_pool().__len__(), 1); # the empty address of <SELF> module



def test_compile_script_borrow_local():
    code = """
        main() {
            let x: u64;
            let ref_x: &u64;
            x = 3;
            ref_x = &x;
            _ = move(ref_x);
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert_equal(count_locals(compiled_script), 2)
    assert(compiled_script.struct_handles().__len__() == 0)
    assert_equal(compiled_script.function_handles().__len__(), 1)
    assert(compiled_script.type_signatures().__len__() == 0)
    assert_equal(compiled_script.function_signatures().__len__(), 1); # method sig
    assert_equal(compiled_script.locals_signatures().__len__(), 1); # local variables sig
    assert_equal(compiled_script.module_handles().__len__(), 1); # the <SELF> module
    assert_equal(compiled_script.identifiers().__len__(), 2); # the name of `main()` + the name of the "<SELF>" module
    assert_equal(compiled_script.address_pool().__len__(), 1); # the empty address of <SELF> module



def test_compile_script_borrow_local_mutable():
    code = """
        main() {
            let x: u64;
            let ref_x: &mut u64;
            x = 3;
            ref_x = &mut x;
            *move(ref_x) = 42;
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert_equal(count_locals(compiled_script), 2)
    assert(compiled_script.struct_handles().__len__() == 0)
    assert_equal(compiled_script.function_handles().__len__(), 1)
    assert(compiled_script.type_signatures().__len__() == 0)
    assert_equal(compiled_script.function_signatures().__len__(), 1); # method sig
    assert_equal(compiled_script.locals_signatures().__len__(), 1); # local variables sig
    assert_equal(compiled_script.module_handles().__len__(), 1); # the <SELF> module
    assert_equal(compiled_script.identifiers().__len__(), 2); # the name of `main()` + the name of the "<SELF>" module
    assert_equal(compiled_script.address_pool().__len__(), 1); # the empty address of <SELF> module



def test_compile_script_borrow_reference():
    code = """
        main() {
            let x: u64;
            let ref_x: &u64;
            let ref_ref_x: &u64;
            x = 3;
            ref_x = &x;
            ref_ref_x = &ref_x;
            return;
        }
    """
    compiled_script_res = compile_script_string_and_assert_error(code, [])
    compiled_script = compiled_script_res
    assert_equal(count_locals(compiled_script), 3)
    assert(compiled_script.struct_handles().__len__() == 0)
    assert_equal(compiled_script.function_handles().__len__(), 1)
    assert(compiled_script.type_signatures().__len__() == 0)
    assert_equal(compiled_script.function_signatures().__len__(), 1); # method sig
    assert_equal(compiled_script.locals_signatures().__len__(), 1); # local variables sig
    assert_equal(compiled_script.module_handles().__len__(), 1); # the <SELF> module
    assert_equal(compiled_script.identifiers().__len__(), 2); # the name of `main()` + the name of the "<SELF>" module
    assert_equal(compiled_script.address_pool().__len__(), 1); # the empty address of <SELF> module



def test_compile_assert():
    code = """
        main() {
            let x: u64;
            x = 3;
            assert(copy(x) > 2, 42);
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    _compiled_script = compiled_script_res



def test_single_resource():
    code = """
module Test {
    resource T { i: u64 }

    public new_t(): Self.T {
        return T { i: 0 };
    }
}
    """
    compiled_module = compile_module_string(code)
    assert_equal(compiled_module.struct_handles().__len__(), 1)



def test_compile_immutable_borrow_local():
    code = """
        main() {
            let x: u64;
            let ref_x: &u64;

            x = 5;
            ref_x = &x;

            _ = move(ref_x);

            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.IMM_BORROW_LOC) == 1)



def test_compile_borrow_field():
    code = """
        module Foobar {
            resource FooCoin { value: u64 }

            public borrow_immut_field(arg: &Self.FooCoin) {
                let field_ref: &u64;
                field_ref = &move(arg).value;
                _ = move(field_ref);
                return;
            }

            public borrow_immut_field_from_mut_ref(arg: &mut Self.FooCoin) {
                let field_ref: &u64;
                field_ref = &move(arg).value;
                _ = move(field_ref);
                return;
            }

            public borrow_mut_field(arg: &mut Self.FooCoin) {
                let field_ref: &mut u64;
                field_ref = &mut move(arg).value;
                _ = move(field_ref);
                return;
            }
        }
    """
    compiled_module_res = compile_module_string(code)
    _compiled_module = compiled_module_res
