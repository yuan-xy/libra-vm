from stdlib import stdlib_modules, build_stdlib_map
from bytecode_verifier import UnusedEntryChecker
from libra.identifier import Identifier
from libra.vm_error import StatusCode
from libra_vm.file_format import (
    CompiledModule, FieldDefinition, IdentifierIndex, LocalsSignature, ModuleHandleIndex,
    SignatureToken, StructHandle, StructHandleIndex, TypeSignature, TypeSignatureIndex
    )
from libra_vm.file_format_common import SerializedType

def test_unused_locals_signature():

    def unused_locals_signature(module: CompiledModule):
        module = module.into_inner()
        module.locals_signatures.append(LocalsSignature([]))
        module = module.freeze()
        unused_entry_checker = UnusedEntryChecker.new(module)
        errors = unused_entry_checker.verify()
        assert len(errors) > 0

    for file, module in build_stdlib_map().items():
        print(file)
        unused_locals_signature(module)


def test_unused_type_signature():

    def unused_type_signature(module):
        module = module.into_inner()
        module.type_signatures.append(TypeSignature(SignatureToken(SerializedType.BOOL)))
        module = module.freeze()
        unused_entry_checker = UnusedEntryChecker.new(module)
        errors = unused_entry_checker.verify()
        assert len(errors) > 0

    for module in stdlib_modules():
        unused_type_signature(module.v0)


def test_unused_field():

    def unused_field(module):
        module = module.into_inner()

        type_sig_idx = module.type_signatures.__len__()
        module.type_signatures.append(TypeSignature(SignatureToken(SerializedType.BOOL)))

        struct_name_idx = module.identifiers.__len__()
        module.identifiers.append("foo")

        field_name_idx = module.identifiers.__len__()
        module.identifiers.append("bar")

        sh_idx = module.struct_handles.__len__()
        module.struct_handles.append(StructHandle(
            module= ModuleHandleIndex.new(0),
            name= IdentifierIndex.new(struct_name_idx),
            is_nominal_resource= False,
            type_formals= [],
        ))

        module.field_defs.append(FieldDefinition(
            struct_= StructHandleIndex.new(sh_idx),
            name= IdentifierIndex.new(field_name_idx),
            signature= TypeSignatureIndex.new(type_sig_idx),
        ))

        module = module.freeze()
        unused_entry_checker = UnusedEntryChecker.new(module)

        errs = unused_entry_checker.verify()
        unused_fields = [x for x in errs if x.major_status == StatusCode.UNUSED_FIELD]
        unused_type_signature = [x for x in errs if x.major_status == StatusCode.UNUSED_TYPE_SIGNATURE]

        assert len(unused_fields) == 1
        assert len(unused_type_signature) == 2 or len(unused_type_signature) == 1

    for file, module in build_stdlib_map().items():
        print(file)
        unused_field(module)

    for module in stdlib_modules():
        unused_field(module.v0)
