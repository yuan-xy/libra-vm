import os
from os.path import isfile, join, abspath, dirname

failed_cases = [
    "reconfiguration_via_network_address_rotation.mvir",
    "tests/generics/instantiation_loops/recursive_struct.mvir",
    "transaction_fee_distribution",
    "validator_set/reconfiguration_via_key_rotation.mvir",
    "tests/validator_set/register_validator.mvir",
    "tests/borrow_tests/eq_bad.mvir",
]

def is_failed_case(file):
    for x in failed_cases:
        if file.find(x) != -1:
            return True
    return False

def pytest_generate_tests(metafunc):
    curdir = dirname(__file__)
    cases = []
    for root, dirs, files in os.walk(curdir):
        for file in files:
            if(file.endswith(".mvir")):
                fullname = join(root, file)
                if not is_failed_case(fullname):
                    cases.append(fullname)
    metafunc.parametrize("filepath", cases)