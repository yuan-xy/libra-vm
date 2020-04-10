import os
from os import listdir
from os.path import isfile, join, abspath, dirname

def pytest_generate_tests(metafunc):
    basedir = "ir-testsuite"
    basedir = "../../libra/language/ir-testsuite/tests"
    curdir = dirname(__file__)
    path = join(curdir, basedir)
    cases = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if(file.endswith(".mvir")):
                fullname = join(root, file)
                cases.append(fullname)
    metafunc.parametrize("filepath", cases)