from bytecode_verifier import CodeUnitVerifier
from libra.vm_error import StatusCode
from vm.file_format import *
from vm.file_format_common import Opcodes
from libra.rustlib import assert_equal


def test_one_pop_no_push():
    module = dummy_procedure_module([Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)])
    errors = CodeUnitVerifier.verify(module)
    print(errors)
    assert_equal(
        errors[0].major_status,
        StatusCode.NEGATIVE_STACK_SIZE_WITHIN_BLOCK
    )



def test_one_pop_one_push():
    # Height: 0 + (-1 + 1) = 0 would have passed original usage verifier
    module = dummy_procedure_module([Bytecode(Opcodes.READ_REF), Bytecode(Opcodes.RET)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(
        errors[0].major_status,
        StatusCode.NEGATIVE_STACK_SIZE_WITHIN_BLOCK
    )



def test_two_pop_one_push():
    # Height: 0 + 1 + (-2 + 1) = 0 would have passed original usage verifier
    module = dummy_procedure_module(
        [Bytecode(Opcodes.LD_U64, 0), Bytecode(Opcodes.ADD), Bytecode(Opcodes.RET)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(
        errors[0].major_status,
        StatusCode.NEGATIVE_STACK_SIZE_WITHIN_BLOCK
    )



def test_two_pop_no_push():
    module = dummy_procedure_module([Bytecode(Opcodes.WRITE_REF), Bytecode(Opcodes.RET)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(
        errors[0].major_status,
        StatusCode.NEGATIVE_STACK_SIZE_WITHIN_BLOCK
    )

