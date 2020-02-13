from libra_vm.file_format import CompiledScript, CompiledModule
from libra.transaction import Script
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname


def test_std_script():
    curdir = dirname(__file__)
    sdir = join(curdir, "stdlib_scripts")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        ser_deser_script(filename)

def ser_deser_script(filename):
    with open(filename, 'r') as file:
        amap = json.load(file)
        code = bytes(amap['code'])
        placeholder_program = Script(code, [])
        obj = CompiledScript.deserialize(placeholder_program.code)
        bstr = obj.serialize()
        assert code == bstr


def test_std_module():
    curdir = dirname(__file__)
    sdir = join(curdir, "stdlib_modules")
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        ser_deser_module(filename)

def ser_deser_module(filename):
    print(filename)
    with open(filename, 'r') as file:
        amap = json.load(file)
        code = bytes(amap['code'])
        obj = CompiledModule.deserialize(code)
        print(obj)
        bstr = obj.serialize()
        print(bstr)
        assert code == bstr


