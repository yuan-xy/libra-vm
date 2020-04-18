from mol.vm.file_format import *
from mol.vm.file_format_common import Opcodes
from libra.transaction import Script
import os


def test_placeholder_script_deserialize():
    curdir = os.path.dirname(__file__)
    filename = os.path.abspath((os.path.join(curdir, "placeholder_script.mvbin")))
    with open(filename, 'rb') as file:
        code = file.read()
        placeholder_program = Script(code, [])
        obj = CompiledScript.deserialize(placeholder_program.code)
        bstr = obj.serialize()
        assert code == bstr


def test_basic_test_module():
    module = basic_test_module()
    bstr = module.serialize()
    obj = CompiledModule.deserialize(bstr)
    assert obj.v0 == module

def test_dummy_procedure_module():
    module = dummy_procedure_module([Bytecode(Opcodes.RET)])
    bstr = module.serialize()
    obj = CompiledModule.deserialize(bstr)
    assert obj == module

def test_empty_script():
    script = empty_script()
    bstr = script.serialize()
    obj = CompiledScript.deserialize(bstr)
    assert obj.v0 == script

