from vm.file_format import CompiledScript, CompiledModule
from stdlib import parse_stdlib_file
from libra.transaction import Script
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname


def test_std_script():
    curdir = dirname(__file__)
    sdir = join(curdir, "../../stdlib/staged/transaction_scripts")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        ser_deser_script(filename)

def ser_deser_script(filename):
    with open(filename, 'rb') as file:
        code = file.read()
        placeholder_program = Script(code, [])
        obj = CompiledScript.deserialize(placeholder_program.code)
        bstr = obj.serialize()
        assert code == bstr


def test_std_module():
    modules = parse_stdlib_file()
    for code in modules:
        obj = CompiledModule.deserialize(code)
        bstr = obj.serialize()
        assert code == bstr

