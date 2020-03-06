
from bytecode_verifier import SignatureChecker
from bytecode_verifier import VerifiedModule
# from invalid_mutations.signature.{
#     ApplySignatureDoubleRefContext, ApplySignatureFieldRefContext, DoubleRefMutation,
#     FieldRefMutation,
# }
from libra.account_address import Address, ADDRESS_LENGTH
from libra.identifier import Identifier
from libra.vm_error import StatusCode

from libra_vm.file_format import *
from libra_vm.signature_token_help import *
from libra_vm import IndexKind, Opcodes, SerializedNativeStructFlag, SerializedType


def test_reference_of_reference():
    m = basic_test_module()
    m.locals_signatures[0] = LocalsSignature([Reference(Reference(
        BOOL,
    ))])
    errors = SignatureChecker(m.freeze()).verify()
    assert errors.__len__() > 0


"""
proptest! {

    def valid_signatures(module in CompiledModule.valid_strategy(20)) {
        signature_checker = SignatureChecker.new(&module)
        prop_assert_equal(signature_checker.verify(), [])
    }


    def double_refs(
        module in CompiledModule.valid_strategy(20),
        mutations in vec(DoubleRefMutation.strategy(), 0..40),
    ) {
        module = module.into_inner()
        expected_violations = {
            context = ApplySignatureDoubleRefContext.new(module, mutations)
            context.apply()
        }
        expected_violations.sort()
        module = module.freeze().expect("should satisfy bounds checker")

        signature_checker = SignatureChecker.new(&module)

        actual_violations = signature_checker.verify()
        # Since some type signatures are field definition references as well, actual_violations
        # will also contain VMStaticViolation.InvalidFieldDefReference errors -- filter those
        # out.
        actual_violations = List[_] = actual_violations
            .into_iter()
            .filter(|err| err.major_status != StatusCode.INVALID_FIELD_DEF)
            .collect()
        actual_violations.sort()
        # The error messages are slightly different from the invalid mutations, so clean these out
        for violation in actual_violations.iter_mut() {
            violation.set_message("".to_string())
        }
        for violation in expected_violations.iter_mut() {
            violation.set_message("".to_string())
        }
        prop_assert_equal(expected_violations, actual_violations)
    }


    def field_def_references(
        module in CompiledModule.valid_strategy(20),
        mutations in vec(FieldRefMutation.strategy(), 0..40),
    ) {
        module = module.into_inner()
        expected_violations = {
            context = ApplySignatureFieldRefContext.new(module, mutations)
            context.apply()
        }
        expected_violations.sort()
        module = module.freeze().expect("should satisfy bounds checker")

        signature_checker = SignatureChecker.new(&module)

        actual_violations = signature_checker.verify()
        # Note that this shouldn't cause any InvalidSignatureToken errors because there are no
        # double references involved. So no filtering is required here.
        actual_violations.sort()
        # The error messages are slightly different from the invalid mutations, so clean these out
        for violation in actual_violations.iter_mut() {
            violation.set_message("".to_string())
        }
        for violation in expected_violations.iter_mut() {
            violation.set_message("".to_string())
        }
        prop_assert_equal(expected_violations, actual_violations)
    }
}
"""

def test_no_verify_locals_good():
    compiled_module_good = CompiledModuleMut(
        module_handles = [ModuleHandle(
            address = AddressPoolIndex(0),
            name = IdentifierIndex(0),
        )],
        struct_handles = [],
        function_handles = [
            FunctionHandle(
                module = ModuleHandleIndex(0),
                name = IdentifierIndex(1),
                signature = FunctionSignatureIndex(0),
            ),
            FunctionHandle(
                module = ModuleHandleIndex(0),
                name = IdentifierIndex(2),
                signature = FunctionSignatureIndex(1),
            ),
        ],
        type_signatures = [],
        function_signatures = [
            FunctionSignature(
                return_types = [],
                arg_types = [ADDRESS],
                type_formals = [],
            ),
            FunctionSignature(
                return_types = [],
                arg_types = [U64],
                type_formals = [],
            ),
        ],
        locals_signatures = [LocalsSignature([ADDRESS]), LocalsSignature([U64])],
        identifiers = [
            "Bad",
            "blah",
            "foo",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
        struct_defs = [],
        field_defs = [],
        function_defs = [
            FunctionDefinition(
                function = FunctionHandleIndex(0),
                flags = 1,
                acquires_global_resources = [],
                code = CodeUnit(
                    max_stack_size = 0,
                    locals = LocalsSignatureIndex(0),
                    code = [Bytecode(Opcodes.RET)],
                ),
            ),
            FunctionDefinition(
                function = FunctionHandleIndex(1),
                flags = 0,
                acquires_global_resources = [],
                code = CodeUnit(
                    max_stack_size = 0,
                    locals = LocalsSignatureIndex(1),
                    code = [Bytecode(Opcodes.RET)],
                ),
            ),
        ],
    )
    VerifiedModule.new(compiled_module_good.freeze())
    errors = SignatureChecker(compiled_module_good.freeze()).verify()
    assert errors.__len__() == 0



def test_no_verify_locals_bad1():
    # This test creates a function with one argument of type Address and
    # a vector of locals containing a single entry of type U64. The function
    # must fail verification since the argument type at position 0 is different
    # from the local type at position 0.
    compiled_module_bad1 = CompiledModuleMut(
        module_handles = [ModuleHandle(
            address = AddressPoolIndex(0),
            name = IdentifierIndex(0),
        )],
        struct_handles = [],
        function_handles = [FunctionHandle(
            module = ModuleHandleIndex(0),
            name = IdentifierIndex(1),
            signature = FunctionSignatureIndex(0),
        )],
        type_signatures = [],
        function_signatures = [FunctionSignature(
            return_types = [],
            arg_types = [ADDRESS],
            type_formals = [],
        )],
        locals_signatures = [LocalsSignature([U64])],
        identifiers = [
            "Bad",
            "blah",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
        struct_defs = [],
        field_defs = [],
        function_defs = [FunctionDefinition(
            function = FunctionHandleIndex(0),
            flags = 1,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 0,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        )],
    )
    #TTODO: should raise error
    VerifiedModule.new(compiled_module_bad1.freeze())




def test_no_verify_locals_bad2():
    # This test creates a function with one argument of type Address and
    # an empty vector of locals. The function must fail verification since
    # number of arguments is greater than the number of locals.
    compiled_module_bad2 = CompiledModuleMut(
        module_handles = [ModuleHandle(
            address = AddressPoolIndex(0),
            name = IdentifierIndex(0),
        )],
        struct_handles = [],
        function_handles = [FunctionHandle(
            module = ModuleHandleIndex(0),
            name = IdentifierIndex(1),
            signature = FunctionSignatureIndex(0),
        )],
        type_signatures = [],
        function_signatures = [FunctionSignature(
            return_types = [],
            arg_types = [ADDRESS],
            type_formals = [],
        )],
        locals_signatures = [LocalsSignature([])],
        identifiers = [
            "Bad",
            "blah",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
        struct_defs = [],
        field_defs = [],
        function_defs = [FunctionDefinition(
            function = FunctionHandleIndex(0),
            flags = 1,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 0,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        )],
    )
    VerifiedModule.new(compiled_module_bad2.freeze())


def test_no_verify_locals_bad3():
    # This test creates a function with one argument of type Address and
    # a vector of locals containing two types, U64 and Address. The function
    # must fail verification since the argument type at position 0 is different
    # from the local type at position 0.
    compiled_module_bad1 = CompiledModuleMut(
        module_handles = [ModuleHandle(
            address = AddressPoolIndex(0),
            name = IdentifierIndex(0),
        )],
        struct_handles = [],
        function_handles = [FunctionHandle(
            module = ModuleHandleIndex(0),
            name = IdentifierIndex(1),
            signature = FunctionSignatureIndex(0),
        )],
        type_signatures = [],
        function_signatures = [FunctionSignature(
            return_types = [],
            arg_types = [ADDRESS],
            type_formals = [],
        )],
        locals_signatures = [LocalsSignature([U64, ADDRESS])],
        identifiers = [
            "Bad",
            "blah",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
        struct_defs = [],
        field_defs = [],
        function_defs = [FunctionDefinition(
            function = FunctionHandleIndex(0),
            flags = 1,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 0,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        )],
    )
    VerifiedModule.new(compiled_module_bad1.freeze())



def test_no_verify_locals_bad4():
    # This test creates a function with two arguments of type U64 and Address and
    # a vector of locals containing three types, U64, U64 and Address. The function
    # must fail verification since the argument type at position 0 is different
    # from the local type at position 0.
    compiled_module_bad1 = CompiledModuleMut(
        module_handles = [ModuleHandle(
            address = AddressPoolIndex(0),
            name = IdentifierIndex(0),
        )],
        struct_handles = [],
        function_handles = [FunctionHandle(
            module = ModuleHandleIndex(0),
            name = IdentifierIndex(1),
            signature = FunctionSignatureIndex(0),
        )],
        type_signatures = [],
        function_signatures = [FunctionSignature(
            return_types = [],
            arg_types = [U64, ADDRESS],
            type_formals = [],
        )],
        locals_signatures = [LocalsSignature([U64, U64, ADDRESS])],
        identifiers = [
            "Bad",
            "blah",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
        struct_defs = [],
        field_defs = [],
        function_defs = [FunctionDefinition(
            function = FunctionHandleIndex(0),
            flags = 1,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 0,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        )],
    )
    VerifiedModule.new(compiled_module_bad1.freeze())
