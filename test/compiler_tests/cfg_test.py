from .testutils import *
from vm.file_format import *
from vm import Opcodes, ScriptAccess
from bytecode_verifier.control_flow_graph import ControlFlowGraph, VMControlFlowGraph
import pytest

def println(str, *args):
    print(str.format(*args))

def test_cfg_compile_script_ret():
    code = """
        main(){
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 1)
    assert_equal(cfg.num_blocks(), 1)
    assert_equal(cfg.reachable_from(0).__len__(), 1)



def test_cfg_compile_script_let():
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
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 1)
    assert_equal(cfg.num_blocks(), 1)
    assert_equal(cfg.reachable_from(0).__len__(), 1)



def test_cfg_compile_if():
    code = """
        main() {
            let x: u64;
            x = 0;
            if (42 > 0) {
                x = 1;
            }
            return;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 3)
    assert_equal(cfg.num_blocks(), 3)
    assert_equal(cfg.reachable_from(0).__len__(), 3)



def test_cfg_compile_if_else():
    code = """
        main() {
            let x: u64;
            let y: u64;
            if (42 > 0) {
                x = 1;
                y = 2;
            } else {
                y = 2;
                x = 1;
            }
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 4)
    assert_equal(cfg.num_blocks(), 4)
    assert_equal(cfg.reachable_from(0).__len__(), 4)



def test_cfg_compile_if_else_with_else_return():
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
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 4)
    assert_equal(cfg.num_blocks(), 4)
    assert_equal(cfg.reachable_from(0).__len__(), 4)



def test_cfg_compile_nested_if():
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
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 6)
    assert_equal(cfg.num_blocks(), 6)
    assert_equal(cfg.reachable_from(7).__len__(), 4)



def test_cfg_compile_if_else_with_if_return():
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
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 3)
    assert_equal(cfg.num_blocks(), 3)
    assert_equal(cfg.reachable_from(0).__len__(), 3)
    assert_equal(cfg.reachable_from(4).__len__(), 1)
    assert_equal(cfg.reachable_from(5).__len__(), 1)



def test_cfg_compile_if_else_with_two_returns():
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
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 4)
    assert_equal(cfg.num_blocks(), 4)
    assert_equal(cfg.reachable_from(0).__len__(), 3)
    assert_equal(cfg.reachable_from(4).__len__(), 1)
    assert_equal(cfg.reachable_from(5).__len__(), 1)
    assert_equal(cfg.reachable_from(6).__len__(), 1)



def test_cfg_compile_if_else_with_else_abort():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                x = 1;
            } else {
                abort 0;
            }
            abort 0;
        }
    """

    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 4)
    assert_equal(cfg.num_blocks(), 4)
    assert_equal(cfg.reachable_from(0).__len__(), 4)



def test_cfg_compile_if_else_with_if_abort():
    code = """
        main() {
            let x: u64;
            if (42 > 0) {
                abort 0;
            } else {
                x = 1;
            }
            abort 0;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 3)
    assert_equal(cfg.num_blocks(), 3)
    assert_equal(cfg.reachable_from(0).__len__(), 3)
    assert_equal(cfg.reachable_from(4).__len__(), 1)
    assert_equal(cfg.reachable_from(6).__len__(), 1)



def test_cfg_compile_if_else_with_two_aborts():
    code = """
        main() {
            if (42 > 0) {
                abort 0;
            } else {
                abort 0;
            }
            abort 0;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    cfg: VMControlFlowGraph = VMControlFlowGraph.new(compiled_script.main().code.code)
    println("SCRIPT:\n {}", compiled_script)
    cfg.display()
    assert_equal(cfg.blocks.__len__(), 4)
    assert_equal(cfg.num_blocks(), 4)
    assert_equal(cfg.reachable_from(0).__len__(), 3)
    assert_equal(cfg.reachable_from(4).__len__(), 1)
    assert_equal(cfg.reachable_from(6).__len__(), 1)
    assert_equal(cfg.reachable_from(8).__len__(), 1)

