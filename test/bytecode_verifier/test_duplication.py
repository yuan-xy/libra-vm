from bytecode_verifier import DuplicationChecker
from libra_vm.file_format import CompiledModule
from stdlib import stdlib_modules, build_stdlib_map

def test_valid_duplication():

    def valid_duplication(module: CompiledModule):
        duplication_checker = DuplicationChecker(module)
        errors = duplication_checker.verify()
        assert len(errors) == 0 #TTODO: why rust test prop_assert!(!errors.is_empty());

    for file, module in build_stdlib_map().items():
        print(file)
        valid_duplication(module)
