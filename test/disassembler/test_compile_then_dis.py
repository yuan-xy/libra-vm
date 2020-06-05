from mol.disassembler.main import main as dis_main
from mol.compiler.main import main as compiler_main
import os
from os.path import join, dirname
import sys
from pathlib import Path


def test_compile_then_disassemble():
    curdir = dirname(__file__)
    # filename = join(curdir, "../../mol/compiler/ir_stdlib/modules/libra_time.mvir")
    filename = join(curdir, "../../ir-testsuite/option.mvir")
    mvfile = Path(filename).with_suffix(".mv")
    if mvfile.exists():
        os.remove(mvfile)
    sys.argv = sys.argv[:1]
    sys.argv.append(filename)
    compiler_main()
    assert mvfile.exists()

    sys.argv = sys.argv[:1]
    sys.argv.extend(["-b", mvfile.as_posix()])
    dis_main()
    os.remove(mvfile)
