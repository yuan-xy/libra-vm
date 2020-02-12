from libra_vm.file_format import CompiledScript
from libra.transaction import Script
import os


def test_placeholder_script_deserialize():
    curdir = os.path.dirname(__file__)
    filename = os.path.abspath((os.path.join(curdir, "placeholder_script.mvbin")))
    with open(filename, 'rb') as file:
        code = file.read()
        placeholder_program = Script(code, [])
        obj = CompiledScript.deserialize(placeholder_program.code)
        print(obj)
        bstr = obj.serialize()
        print(bstr)
        assert code == bstr

