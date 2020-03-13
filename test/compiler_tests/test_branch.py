from __future__ import annotations
from .testutils import compile_script_string
from libra_vm.file_format import *
from libra_vm import Opcodes


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


"""
def test_compile_if_else() {
    code = String.from(
        "
        main() {
            x: Uint64
            y: Uint64
            if (42 > 0) {
                x = 1
            else:
                y = 1
            }
            return
        }
        ",
    )

    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
}


def test_compile_nested_if_else() {
    code = String.from(
        "
        main() {
            x: Uint64
            if (42 > 0) {
                x = 1
            else:
                if (5 > 10) {
                    x = 2
                else:
                    x = 3
                }
            }
            return
        }
        ",
    )

    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
}


def test_compile_if_else_with_if_return() {
    code = String.from(
        "
        main() {
            x: Uint64
            if (42 > 0) {
                return
            else:
                x = 1
            }
            return
        }
        ",
    )

    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 0)
    assert(instr_count(compiled_script, Ret) == 2)
}


def test_compile_if_else_with_else_return() {
    code = String.from(
        "
        main() {
            x: Uint64
            if (42 > 0) {
                x = 1
            else:
                return
            }
            return
        }
        ",
    )

    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
    assert(instr_count(compiled_script, Ret) == 2)
}


def test_compile_if_else_with_two_returns() {
    code = String.from(
        "
        main() {
            if (42 > 0) {
                return
            else:
                return
            }
            return
        }
        ",
    )

    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 0)
    assert(instr_count(compiled_script, Ret) == 3)
}


def test_compile_while() {
    code = String.from(
        "
        main() {
            x: Uint64
            x = 0
            while (copy(x) < 5) {
                x = copy(x) + 1
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
}


def test_compile_while_return() {
    code = String.from(
        "
        main() {
            while (42 > 0) {
                return
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
    assert(instr_count(compiled_script, Ret) == 2)
}


def test_compile_nested_while() {
    code = String.from(
        "
        main() {
            x: Uint64
            y: Uint64
            x = 0
            while (copy(x) < 5) {
                x = move(x) + 1
                y = 0
                while (copy(y) < 5) {
                    y = move(y) + 1
                }
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
}


def test_compile_break_outside_loop() {
    code = String.from(
        "
        main() {
            break
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    assert(compiled_script_res.is_err())
}


def test_compile_continue_outside_loop() {
    code = String.from(
        "
        main() {
            continue
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    assert(compiled_script_res.is_err())
}


def test_compile_while_break() {
    code = String.from(
        "
        main() {
            while (True) {
                break
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
}


def test_compile_while_continue() {
    code = String.from(
        "
        main() {
            while (False) {
                continue
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 1)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
}


def test_compile_while_break_continue() {
    code = String.from(
        "
        main() {
            x: Uint64
            x = 42
            while (False) {
                x = move(x) / 3
                if (copy(x) == 0) {
                    break
                }
                continue
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 2)
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 3)
}


def test_compile_loop_empty() {
    code = String.from(
        "
        main() {
            loop {
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 1)
}


def test_compile_loop_nested_break() {
    code = String.from(
        "
        main() {
            loop {
                loop {
                    break
                }
                break
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 4)
}


def test_compile_loop_continue() {
    code = String.from(
        "
        main() {
            loop {
                continue
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
}


def test_compile_loop_break_continue() {
    code = String.from(
        "
        main() {
            x: Uint64
            y: Uint64
            x = 0
            y = 0

            loop {
                x = move(x) + 1
                if (copy(x) >= 10) {
                    break
                }
                if (copy(x) % 2 == 0) {
                    continue
                }
                y = move(y) + copy(x)
            }

            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 3)
    assert(instr_count(compiled_script, Opcodes.BrFalse) == 2)
}


def test_compile_loop_return() {
    code = String.from(
        "
        main() {
            loop {
                loop {
                    return
                }
                return
            }
            return
        }
        ",
    )
    compiled_script_res = compile_script_string(&code)
    compiled_script = compiled_script_res
    assert(instr_count(compiled_script, Opcodes.BRANCH) == 2)
    assert(instr_count(compiled_script, Ret) == 3)
}
"""