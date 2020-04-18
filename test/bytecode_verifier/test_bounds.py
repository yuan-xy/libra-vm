from mol.vm.check_bounds import BoundsChecker
from mol.vm.file_format import *
from mol.vm.file_format_common import Opcodes
from mol.vm.signature_token_help import *
from libra.rustlib import *
import pytest

def test_empty_module_no_errors():
    basic_test_module().freeze()


def test_invalid_type_param_in_fn_return_types():
    m = basic_test_module()
    m.function_signatures[0].return_types = [TypeParameter(0)]
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_type_param_in_fn_arg_types():
    m = basic_test_module()
    m.function_signatures[0].arg_types = [TypeParameter(0)]
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_struct_in_fn_return_types():
    m = basic_test_module()
    m.function_signatures[0].return_types = [Struct((StructHandleIndex.new(1), []))]
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_type_param_in_field():
    m = basic_test_module()
    m.type_signatures[0].v0 = TypeParameter(0)
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_struct_in_field():
    m = basic_test_module()
    m.type_signatures[0].v0 = Struct((StructHandleIndex.new(3), []))
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_struct_with_actuals_in_field():
    m = basic_test_module()
    m.type_signatures[0].v0 = Struct((StructHandleIndex.new(0), [TypeParameter(0)]))
    with pytest.raises(VMException) as excinfo:
        m.freeze()


def test_invalid_locals_id_in_call():
    m = basic_test_module()
    m.function_defs[0].code.code = [Bytecode(Opcodes.CALL, (
        FunctionHandleIndex.new(0),
        LocalsSignatureIndex.new(1),
    ))]
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_type_param_in_call():
    m = basic_test_module()
    m.locals_signatures.append(LocalsSignature([TypeParameter(0)]))
    m.function_defs[0].code.code = [Bytecode(Opcodes.CALL, (
        FunctionHandleIndex.new(0),
        LocalsSignatureIndex.new(1),
    ))]
    with pytest.raises(VMException) as excinfo:
        m.freeze()



def test_invalid_struct_as_type_actual_in_exists():
    m = basic_test_module()
    m.locals_signatures.append(LocalsSignature([Struct((
        StructHandleIndex.new(3),
        [],
    ))]))
    m.function_defs[0].code.code = [Bytecode(Opcodes.CALL, (
        FunctionHandleIndex.new(0),
        LocalsSignatureIndex.new(1),
    ))]
    with pytest.raises(VMException) as excinfo:
        m.freeze()


def test_no_module_handles():

    def no_module_handles(
        identifiers,
        address_pool,
        byte_array_pool,
    ):
        # If there are no module handles, the only other things that can be stored are intrinsic
        # data.
        module = CompiledModuleMut.default()
        module.identifiers = identifiers
        module.address_pool = address_pool
        module.byte_array_pool = byte_array_pool

        bounds_checker = BoundsChecker(module)
        actual_violations: List[StatusCode] = [x.major_status for x in bounds_checker.verify()]
        assert_equal(
            actual_violations,
            [StatusCode.NO_MODULE_HANDLES]
        )

    for p1 in [[],[""], ["1", "22"]]:
        for p2 in [[], [Address.default()]]:
            for p3 in [[],[b""], [b"1", b"22"]]:
                no_module_handles(p1, p2, p3)


