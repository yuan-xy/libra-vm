from __future__ import annotations
from .testutils import *
from mol.vm.file_format import *
from mol.vm import Opcodes
import pytest

def test_compile_if():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                x = 1;
            }
            return;
        }
        """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 0)



def test_compile_if_else():
    code = """
        main() {
            let x: u64;
            let y: u64;
            if (42 > 0) {
                x = 1;
            } else {
                y = 1;
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)



def test_compile_nested_if_else():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                x = 1;
            } else {
                if (5 > 10) {
                    x = 2;
                } else {
                    x = 3;
                }
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)



def test_compile_if_else_with_if_return():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                return;
            } else {
                x = 1;
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 0)
    assert(instr_count(compiled_script, Opcodes.RET) == 2)



def test_compile_if_else_with_else_return():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                x = 1;
            } else {
                return;
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
    assert(instr_count(compiled_script, Opcodes.RET) == 2)



def test_compile_if_else_with_two_returns():
    code = """
        main() {
            if (42 > 0) {
                return;
            } else {
                return;
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 0)
    assert(instr_count(compiled_script, Opcodes.RET) == 3)



def test_compile_while():
    code = """
        main() {
            let x: u64;
            x = 0;
            while (copy(x) < 5) {
                x = copy(x) + 1;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)



def test_compile_while_return():
    code = """
        main() {
            while (42 > 0) {
                return;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
    assert(instr_count(compiled_script, Opcodes.RET) == 2)



def test_compile_nested_while():
    code = """
        main() {
            let x: u64;
            let y: u64;
            x = 0;
            while (copy(x) < 5) {
                x = move(x) + 1;
                y = 0;
                while (copy(y) < 5) {
                    y = move(y) + 1;
                }
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)



def test_compile_break_outside_loop():
    code = """
        main() {
            break;
            return;
        }
    """
    with pytest.raises(Exception) as excinfo:
        compiled_script_res = compile_script_string(code)



def test_compile_continue_outside_loop():
    code = """
        main() {
            continue;
            return;
        }
    """
    with pytest.raises(Exception) as excinfo:
        compiled_script_res = compile_script_string(code)



def test_compile_while_break():
    code = """
        main() {
            while (true) {
                break;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)



def test_compile_while_continue():
    code = """
        main() {
            while (false) {
                continue;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)



def test_compile_while_break_continue():
    code = """
        main() {
            let x: u64;
            x = 42;
            while (false) {
                x = move(x) / 3;
                if (copy(x) == 0) {
                    break;
                }
                continue;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 3)



def test_compile_loop_empty():
    code = """
        main() {
            loop {
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)



def test_compile_loop_nested_break():
    code = """
        main() {
            loop {
                loop {
                    break;
                }
                break;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 4)



def test_compile_loop_continue():
    code = """
        main() {
            loop {
                continue;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)



def test_compile_loop_break_continue():
    code = """
        main() {
            let x: u64;
            let y: u64;
            x = 0;
            y = 0;

            loop {
                x = move(x) + 1;
                if (copy(x) >= 10) {
                    break;
                }
                if (copy(x) % 2 == 0) {
                    continue;
                }
                y = move(y) + copy(x);
            }

            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 3)
    assert(instr_count(compiled_script, Opcodes.BR_FALSE) == 2)



def test_compile_loop_return():
    code = """
        main() {
            loop {
                loop {
                    return;
                }
                return;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
    assert(instr_count(compiled_script, Opcodes.RET) == 3)
