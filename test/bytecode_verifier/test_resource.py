from stdlib import stdlib_modules, build_stdlib_map
from bytecode_verifier import ResourceTransitiveChecker
from vm.file_format import CompiledModule

def test_valid_resource_transitivity():

    def valid_resource_transitivity(module: CompiledModule):
        resource_checker = ResourceTransitiveChecker.new(module)
        errors = resource_checker.verify()
        assert not errors


    for file, module in build_stdlib_map().items():
        print(file)
        valid_resource_transitivity(module)

