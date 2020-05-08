from libra import Address
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.compiler.bytecode_source_map.utils import source_map_from_file
from mol.functional_tests.ir_compiler import IRCompiler
from mol.functional_tests import testsuite
from pathlib import Path
from os.path import join, dirname

def test_executable_linenos():
    compiler = IRCompiler()
    compiler.output_source_maps = True

    curdir = dirname(__file__)
    filename = join(curdir, "../mol/compiler/ir_stdlib/modules/libra_time.mvir")

    source_path = Path(filename)
    assert source_path.exists()
    source = source_path.read_text()

    testsuite.functional_tests(compiler, filename)

    source_map_path = Path(filename).with_suffix(".mvsm")
    assert source_map_path.exists()
    source_map = source_map_from_file(source_map_path)

    mapping = SourceMapping(source_map, None)
    mapping.with_source_code(filename, source)
    assert sorted(mapping.source_map.executable_linenos()) ==\
        [12, 15, 16, 17, 27, 28, 30, 33, 34, 35, 36, 41]

    sorm = compiler.compile(
        lambda x: print(x),
        bytes.fromhex(source_map.module_name[0]),
        source,
        filename,
    )
    assert sorted(mapping.source_map.executable_linenos()) ==\
         sorted(sorm.source_mapping.source_map.executable_linenos())
    # assert sorm.source_mapping == mapping
    # assert source_map.function_map[0].locls == sorm.source_map.function_map[0].locls

