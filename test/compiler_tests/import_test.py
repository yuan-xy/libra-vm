from .testutils import compile_module_string_with_stdlib, compile_script_string_with_stdlib
from mol.vm.file_format import *
from mol.vm import Opcodes, ScriptAccess
import pytest



def test_compile_script_with_imports():
    code = """
        import 0x0.LibraCoin;

        main() {
            let x: u64;
            let y: u64;
            x = 2;
            y = copy(x) + copy(x);
            return;
        }
    """
    compiled_script_res = compile_script_string_with_stdlib(code)
    _compiled_script = compiled_script_res



def test_compile_module_with_imports():
    code = """
        module Foobar {
            import 0x0.LibraCoin;

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
    compiled_module_res = compile_module_string_with_stdlib(code)
    _compiled_module = compiled_module_res
