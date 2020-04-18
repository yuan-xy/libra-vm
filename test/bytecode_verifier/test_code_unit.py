from mol.bytecode_verifier import CodeUnitVerifier
from libra.vm_error import StatusCode
from mol.vm.file_format import *
from mol.vm.file_format_common import Opcodes
from libra.rustlib import assert_equal


def test_invalid_fallthrough_br_True():
    module = dummy_procedure_module([Bytecode(Opcodes.LD_FALSE), Bytecode(Opcodes.BR_TRUE,1)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(errors[0].major_status, StatusCode.INVALID_FALL_THROUGH)



def test_invalid_fallthrough_br_False():
    module = dummy_procedure_module([Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.BR_FALSE,1)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(errors[0].major_status, StatusCode.INVALID_FALL_THROUGH)


# all non-branch instructions should trigger invalid fallthrough; just check one of them

def test_invalid_fallthrough_non_branch():
    module = dummy_procedure_module([Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP)])
    errors = CodeUnitVerifier.verify(module)
    assert_equal(errors[0].major_status, StatusCode.INVALID_FALL_THROUGH)



def test_valid_fallthrough_branch():
    module = dummy_procedure_module([Bytecode(Opcodes.BRANCH,0)])
    errors = CodeUnitVerifier.verify(module)
    assert not errors



def test_valid_fallthrough_ret():
    module = dummy_procedure_module([Bytecode(Opcodes.RET)])
    errors = CodeUnitVerifier.verify(module)
    assert not errors



def test_valid_fallthrough_abort():
    module = dummy_procedure_module([Bytecode(Opcodes.LD_U64,7), Bytecode(Opcodes.ABORT)])
    errors = CodeUnitVerifier.verify(module)
    assert not errors

