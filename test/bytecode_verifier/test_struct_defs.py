from stdlib import stdlib_modules, build_stdlib_map
from bytecode_verifier import RecursiveStructDefChecker
from vm.file_format import CompiledModule

def test_valid_recursive_struct_defs():

    def valid_recursive_struct_defs(module: CompiledModule):
        recursive_checker = RecursiveStructDefChecker(module)
        errors = recursive_checker.verify()
        assert not errors


    for file, module in build_stdlib_map().items():
        print(file)
        valid_recursive_struct_defs(module)


