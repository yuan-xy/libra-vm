from mol.disassembler.main import main as dis_main
from mol.compiler.main import main as compiler_main
import os
from os.path import join, dirname
import sys
from pathlib import Path
import pytest

@pytest.mark.parametrize(
    'compile_args', [
        ([]),
        (["--src-map"]),
    ]
)
def test_compile_then_disassemble(capsys, compile_args):
    curdir = dirname(__file__)
    # filename = join(curdir, "../../mol/compiler/ir_stdlib/modules/libra_time.mvir")
    filename = join(curdir, "../../ir-testsuite/option.mvir")
    mvfile = Path(filename).with_suffix(".mv")
    mvsmfile = Path(filename).with_suffix(".mvsm")
    if mvfile.exists():
        os.remove(mvfile)
    if mvsmfile.exists():
        os.remove(mvsmfile)

    c_argv = [filename]
    c_argv.extend(compile_args)
    compiler_main(c_argv)
    assert mvfile.exists()
    if compile_args == ["--src-map"]:
        assert mvsmfile.exists()

    d_argv = ["-b", mvfile.as_posix()]
    dis_main(d_argv)
    out = capsys.readouterr().out
    assert "v: vector" in out
    os.remove(mvfile)
    if compile_args == ["--src-map"]:
        assert "public unwrap_or<E: 2>(x: T<E>, e: E): E {" in out
        os.remove(mvsmfile)
