from libra_vm.file_format import CompiledScript, CompiledModule
from libra.transaction import Script
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname


def test_extern_script():
    run_extern_script("../../../libra/language/move-prover")
    run_extern_script("../../../libra/language/stdlib/staged/transaction_scripts")

def run_extern_script(extern_dir):
    curdir = dirname(__file__)
    path = join(curdir, extern_dir)
    for root, dirs, files in os.walk(path):
        for file in files:
            if(file.endswith(".mv")):
                ser_deser_script(join(root, file))


def ser_deser_script(filename):
    print(filename)
    with open(filename, 'rb') as file:
        code = file.read()
        placeholder_program = Script(code, [])
        obj = CompiledScript.deserialize(placeholder_program.code)
        bstr = obj.serialize()
        assert code == bstr


