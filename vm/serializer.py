from __future__ import annotations
from vm.vm_exception import VMException
from vm.errors import *
from vm.file_format import *
from vm.file_format_common import *
from libra.account_address import Address
from libra.identifier import Identifier
from libra.vm_error import StatusCode, VMStatus
from libra.rustlib import ensure
from canoser import Cursor, Uint8, Uint16, Uint32, Uint64, Uint128
from typing import List, Optional, Tuple
from dataclasses import dataclass
import abc


def check_index_in_binary(index: usize) -> Uint32:
    if index > Uint32.max_value:
        bail(
            "Compilation unit too big ({}) cannot exceed {}",
            index,
            Uint32.max_value
        )
    return index


def unchecked_serialize_table(
    binary: BinaryData,
    kind: TableType,
    offset: Uint32,
    count: Uint32,
):
    if count > 0:
        binary.push(kind)
        write_Uint32(binary, offset)
        write_Uint32(binary, count)


def checked_serialize_table(
    binary: BinaryData,
    kind: TableType,
    start: Uint32,
    offset: Uint32,
    length: Uint32,
):
    start_offset = Uint32.checked_add(start, offset)
    if start_offset is not None:
        unchecked_serialize_table(binary, kind, start_offset, length)
    else:
        bail(
            "binary size ({}) cannot exceed {}",
            binary.__len__(),
            Uint32.max_value,
        )


def serialize_magic(binary: BinaryData):
    for byte in BinaryConstants.LIBRA_MAGIC:
        binary.push(byte)


# Serializes a `ModuleHandle`.
#
# A `ModuleHandle` gets serialized as follows:
# - `ModuleHandle.address` as a ULEB128 (index into the `AddressPool`)
# - `ModuleHandle.name` as a ULEB128 (index into the `IdentifierPool`)
def serialize_module_handle(binary: BinaryData, module_handle: ModuleHandle):
    write_Uint16_as_uleb128(binary, module_handle.address.v0)
    write_Uint16_as_uleb128(binary, module_handle.name.v0)


# Serializes a `StructHandle`.
#
# A `StructHandle` gets serialized as follows:
# - `StructHandle.module` as a ULEB128 (index into the `ModuleHandle` table)
# - `StructHandle.name` as a ULEB128 (index into the `IdentifierPool`)
# - `StructHandle.is_nominal_resource` as a 1 byte boolean (0 for False, 1 for True)
def serialize_struct_handle(binary: BinaryData, struct_handle: StructHandle):
    write_Uint16_as_uleb128(binary, struct_handle.module.v0)
    write_Uint16_as_uleb128(binary, struct_handle.name.v0)
    serialize_nominal_resource_flag(binary, struct_handle.is_nominal_resource)
    serialize_kinds(binary, struct_handle.type_formals)


# Serializes a `FunctionHandle`.
#
# A `FunctionHandle` gets serialized as follows:
# - `FunctionHandle.module` as a ULEB128 (index into the `ModuleHandle` table)
# - `FunctionHandle.name` as a ULEB128 (index into the `IdentifierPool`)
# - `FunctionHandle.signature` as a ULEB128 (index into the `FunctionSignaturePool`)
def serialize_function_handle(
    binary: BinaryData,
    function_handle: FunctionHandle,
):
    write_Uint16_as_uleb128(binary, function_handle.module.v0)
    write_Uint16_as_uleb128(binary, function_handle.name.v0)
    write_Uint16_as_uleb128(binary, function_handle.signature.v0)



# Serializes a string (identifier or user string).
#
# A `String` gets serialized as follows:
# - `String` size as a ULEB128
# - `String` bytes - *exact format to be defined, Rust utf8 right now*
def serialize_string(binary: BinaryData, string: str):
    bs = bytes(string, "utf-8")
    length = bs.__len__()
    if length > Uint32.max_value:
        bail("string size ({}) cannot exceed {}", length, Uint32.max_value)

    write_Uint32_as_uleb128(binary, length)
    for byte in bs:
        binary.push(byte)


# Serializes a `ByteArray`.
#
# A `ByteArray` gets serialized as follows:
# - `ByteArray` size as a ULEB128
# - `ByteArray` bytes in increasing index order
def serialize_byte_array(binary: BinaryData, byte_array: bytearray):
    if len(byte_array) > Uint32.max_value:
        bail(
            "byte arrays size ({}) cannot exceed {}",
            len(byte_array),
            Uint32.max_value
        )

    write_Uint32_as_uleb128(binary, len(byte_array))
    binary.extend(byte_array)

# Serializes an `Address`.
#
# A `Address` gets serialized as follows:
# - 32 bytes in increasing index order
def serialize_address(binary: BinaryData, address: Address):
    binary.extend(address)

# Serializes a `StructDefinition`.
#
# A `StructDefinition` gets serialized as follows:
# - `StructDefinition.handle` as a ULEB128 (index into the `ModuleHandle` table)
# - `StructDefinition.field_count` as a ULEB128 (number of fields defined in the type)
# - `StructDefinition.fields` as a ULEB128 (index into the `FieldDefinition` table)
def serialize_struct_definition(
    binary: BinaryData,
    struct_definition: StructDefinition,
):
    write_Uint16_as_uleb128(binary, struct_definition.struct_handle.v0)
    if struct_definition.field_information.tag == SerializedNativeStructFlag.NATIVE:
        binary.push(SerializedNativeStructFlag.NATIVE)
        write_Uint16_as_uleb128(binary, 0)
        write_Uint16_as_uleb128(binary, 0)
    elif struct_definition.field_information.tag == SerializedNativeStructFlag.DECLARED:
        binary.push(SerializedNativeStructFlag.DECLARED)
        write_Uint16_as_uleb128(binary, struct_definition.field_information.field_count)
        write_Uint16_as_uleb128(binary, struct_definition.field_information.fields.v0)
    else:
        bail("unreachable!")


# Serializes a `FieldDefinition`.
#
# A `FieldDefinition` gets serialized as follows:
# - `FieldDefinition.struct_` as a ULEB128 (index into the `StructHandle` table)
# - `StructDefinition.name` as a ULEB128 (index into the `IdentifierPool` table)
# - `StructDefinition.signature` as a ULEB128 (index into the `TypeSignaturePool`)
def serialize_field_definition(
    binary: BinaryData,
    field_definition: FieldDefinition,
):
    write_Uint16_as_uleb128(binary, field_definition.struct_.v0)
    write_Uint16_as_uleb128(binary, field_definition.name.v0)
    write_Uint16_as_uleb128(binary, field_definition.signature.v0)


# Serializes a `FunctionDefinition`.
#
# A `FunctionDefinition` gets serialized as follows:
# - `FunctionDefinition.function` as a ULEB128 (index into the `FunctionHandle` table)
# - `FunctionDefinition.flags` 1 byte for the flags of the function
# - `FunctionDefinition.code` a variable size stream for the `CodeUnit`
def serialize_function_definition(
    binary: BinaryData,
    function_definition: FunctionDefinition,
):
    write_Uint16_as_uleb128(binary, function_definition.function.v0)
    binary.push(function_definition.flags)
    serialize_struct_definition_indices(binary, function_definition.acquires_global_resources)
    serialize_code_unit(binary, function_definition.code)


# Serializes a `List[StructDefinitionIndex]`.
def serialize_struct_definition_indices(
    binary: BinaryData,
    indices: List[StructDefinitionIndex],
):
    length = indices.__len__()
    if length > Uint8.max_value:
        bail(
            "acquires_global_resources size ({}) cannot exceed {}",
            length,
            Uint8.max_value,
        )

    binary.push(length)
    for def_idx in indices:
        write_Uint16_as_uleb128(binary, def_idx.v0)


# Serializes a `TypeSignature`.
#
# A `TypeSignature` gets serialized as follows:
# - `SignatureType.TYPE_SIGNATURE` as 1 byte
# - The `SignatureToken` as a blob
def serialize_type_signature(binary: BinaryData, signature: TypeSignature):
    binary.push(SignatureType.TYPE_SIGNATURE)
    serialize_signature_token(binary, signature.v0)


# Serializes a `FunctionSignature`.
#
# A `FunctionSignature` gets serialized as follows:
# - `SignatureType.FUNCTION_SIGNATURE` as 1 byte
# - The vector of `SignatureToken`s for the return values
# - The vector of `SignatureToken`s for the arguments
def serialize_function_signature(
    binary: BinaryData,
    signature: FunctionSignature,
):
    binary.push(SignatureType.FUNCTION_SIGNATURE)
    serialize_signature_tokens(binary, signature.return_types)
    serialize_signature_tokens(binary, signature.arg_types)
    serialize_kinds(binary, signature.type_formals)


# Serializes a `LocalsSignature`.
#
# A `LocalsSignature` gets serialized as follows:
# - `SignatureType.LOCAL_SIGNATURE` as 1 byte
# - The vector of `SignatureToken`s for locals
def serialize_locals_signature(binary: BinaryData, signature: LocalsSignature):
    binary.push(SignatureType.LOCAL_SIGNATURE)
    serialize_signature_tokens(binary, signature.v0)


# Serializes a slice of `SignatureToken`s.
def serialize_signature_tokens(binary: BinaryData, tokens: List[SignatureToken]):
    length = tokens.__len__()
    if length > Uint8.max_value:
        bail(
            "arguments/locals size ({}) cannot exceed {}",
            length,
            Uint8.max_value,
        )

    binary.push(length)
    for token in tokens:
        serialize_signature_token(binary, token)


# Serializes a `SignatureToken`.
#
# A `SignatureToken` gets serialized as a variable size blob depending on composition.
# Values for types are defined in `SerializedType`.
def serialize_signature_token(binary: BinaryData, token: SignatureToken):
    binary.push(token.tag)
    if token.tag == SerializedType.STRUCT:
        (idx, types) = token.struct
        write_Uint16_as_uleb128(binary, idx.v0)
        serialize_signature_tokens(binary, types)
    elif token.is_reference():
        boxed_token = token.reference
        serialize_signature_token(binary, boxed_token)
    elif token.tag == SerializedType.TYPE_PARAMETER:
        idx = token.typeParameter
        write_Uint16_as_uleb128(binary, idx)
    elif token.tag == SerializedType.VECTOR:
        boxed_token = token.vector_type
        serialize_signature_token(binary, boxed_token)
    elif token.is_primitive():
        pass
    else:
        bail("unreachable!")



def serialize_nominal_resource_flag(
    binary: BinaryData,
    is_nominal_resource: bool,
):
    if is_nominal_resource:
        binary.push(SerializedNominalResourceFlag.NOMINAL_RESOURCE)
    else:
        binary.push(SerializedNominalResourceFlag.NORMAL_STRUCT)


def serialize_kind(binary: BinaryData, kind: Kind):
    if kind == Kind.All:
        binary.push(SerializedKind.ALL)
    elif kind == Kind.Resource:
        binary.push(SerializedKind.RESOURCE)
    elif kind == Kind.Unrestricted:
        binary.push(SerializedKind.UNRESTRICTED)
    else:
        bail("unreachable!")


def serialize_kinds(binary: BinaryData, kinds: List[Kind]):
    write_Uint32_as_uleb128(binary, kinds.__len__())
    for kind in kinds:
        serialize_kind(binary, kind)


# Serializes a `CodeUnit`.
#
# A `CodeUnit` is serialized as the code field of a `FunctionDefinition`.
# A `CodeUnit` gets serialized as follows:
# - `CodeUnit.max_stack_size` as a ULEB128
# - `CodeUnit.locals` as a ULEB128 (index into the `LocalSignaturePool`)
# - `CodeUnit.code` as variable size byte stream for the bytecode
def serialize_code_unit(binary: BinaryData, code: CodeUnit):
    write_Uint16_as_uleb128(binary, code.max_stack_size)
    write_Uint16_as_uleb128(binary, code.locals.v0)
    serialize_code(binary, code.code)


# Serializes a single `Bytecode` instruction.
def serialize_instruction_inner(binary: BinaryData, opcode: Bytecode):
    tag: Opcodes = opcode.tag
    binary.push(tag)
    if tag in [Opcodes.BR_TRUE, Opcodes.BR_FALSE, Opcodes.BRANCH]:
        write_Uint16(binary, opcode.value)
    elif tag == Opcodes.LD_U8:
        binary.push(opcode.value)
    elif tag == Opcodes.LD_U64:
        write_Uint64(binary, opcode.value)
    elif tag == Opcodes.LD_U128:
        write_Uint128(binary, opcode.value)
    elif tag == Opcodes.LD_ADDR:
        write_Uint16_as_uleb128(binary, opcode.value.v0)
    elif tag == Opcodes.LD_BYTEARRAY:
        write_Uint16_as_uleb128(binary, opcode.value.v0)
    elif tag in [Opcodes.COPY_LOC, Opcodes.MOVE_LOC, Opcodes.ST_LOC, Opcodes.MUT_BORROW_LOC, Opcodes.IMM_BORROW_LOC]:
        binary.push(opcode.value)
    elif tag in [Opcodes.MUT_BORROW_FIELD, Opcodes.IMM_BORROW_FIELD]:
        write_Uint16_as_uleb128(binary, opcode.value.v0)
    elif tag == Opcodes.CALL:
        method_idx, types_idx = opcode.value
        write_Uint16_as_uleb128(binary, method_idx.v0)
        write_Uint16_as_uleb128(binary, types_idx.v0)
    elif tag in [Opcodes.PACK, Opcodes.UNPACK, Opcodes.EXISTS, Opcodes.MUT_BORROW_GLOBAL, Opcodes.IMM_BORROW_GLOBAL, Opcodes.MOVE_FROM, Opcodes.MOVE_TO]:
        class_idx, types_idx = opcode.value
        write_Uint16_as_uleb128(binary, class_idx.v0)
        write_Uint16_as_uleb128(binary, types_idx.v0)


# Serializes a `Bytecode` stream. Serialization of the function body.
def serialize_code(binary: BinaryData, code: List[Bytecode]):
    code_size = code.__len__()
    if code_size > Uint16.max_value:
        bail(
            "code size ({}) cannot exceed {}",
            code_size,
            Uint16.max_value,
        )

    write_Uint16(binary, code_size)
    for opcode in code:
        serialize_instruction_inner(binary, opcode)


# Compute the table size with a check for underflow
def checked_calculate_table_size(binary: BinaryData, start: Uint32) -> Uint32:
    offset = check_index_in_binary(binary.__len__())
    ensure(offset >= start, "table start must be before end")
    return offset - start




# Holds data to compute the header of a generic binary.
#
# A binary header contains information about the tables serialized.
# The serializer needs to serialize the tables in order to compute the offset and size
# of each table.
# `CommonSerializer` keeps track of the tables common to `CompiledScript` and
# `CompiledModule`.
@dataclass
class CommonSerializer:
    major_version: Uint8
    minor_version: Uint8
    table_count: Uint8
    module_handles: Tuple[Uint32, Uint32]
    struct_handles: Tuple[Uint32, Uint32]
    function_handles: Tuple[Uint32, Uint32]
    type_signatures: Tuple[Uint32, Uint32]
    function_signatures: Tuple[Uint32, Uint32]
    locals_signatures: Tuple[Uint32, Uint32]
    identifiers: Tuple[Uint32, Uint32]
    address_pool: Tuple[Uint32, Uint32]
    byte_array_pool: Tuple[Uint32, Uint32]

    @classmethod
    def new(cls, major_version: Uint8, minor_version: Uint8) -> CommonSerializer:
        return cls(
            major_version = major_version,
            minor_version = minor_version,
            table_count = 0,
            module_handles = [0, 0],
            struct_handles = [0, 0],
            function_handles = [0, 0],
            type_signatures = [0, 0],
            function_signatures = [0, 0],
            locals_signatures = [0, 0],
            identifiers = [0, 0],
            address_pool = [0, 0],
            byte_array_pool = [0, 0],
        )

    # Common binary header serialization.
    def serialize_header(self, binary: BinaryData) -> Uint32:
        serialize_magic(binary)
        binary.push(self.major_version)
        binary.push(self.minor_version)
        binary.push(self.table_count)

        table_count_op = self.table_count * BinaryConstants.TABLE_HEADER_SIZE
        Uint8.check_value(table_count_op)
        assert binary.__len__() == BinaryConstants.HEADER_SIZE
        checked_start_offset = check_index_in_binary(binary.__len__())
        checked_start_offset += table_count_op
        Uint32.check_value(checked_start_offset)
        start_offset = checked_start_offset

        checked_serialize_table(
            binary,
            TableType.MODULE_HANDLES,
            self.module_handles[0],
            start_offset,
            self.module_handles[1],
        )
        checked_serialize_table(
            binary,
            TableType.STRUCT_HANDLES,
            self.struct_handles[0],
            start_offset,
            self.struct_handles[1],
        )
        checked_serialize_table(
            binary,
            TableType.FUNCTION_HANDLES,
            self.function_handles[0],
            start_offset,
            self.function_handles[1],
        )
        checked_serialize_table(
            binary,
            TableType.TYPE_SIGNATURES,
            self.type_signatures[0],
            start_offset,
            self.type_signatures[1],
        )
        checked_serialize_table(
            binary,
            TableType.FUNCTION_SIGNATURES,
            self.function_signatures[0],
            start_offset,
            self.function_signatures[1],
        )
        checked_serialize_table(
            binary,
            TableType.LOCALS_SIGNATURES,
            self.locals_signatures[0],
            start_offset,
            self.locals_signatures[1],
        )
        checked_serialize_table(
            binary,
            TableType.IDENTIFIERS,
            self.identifiers[0],
            start_offset,
            self.identifiers[1],
        )
        checked_serialize_table(
            binary,
            TableType.ADDRESS_POOL,
            self.address_pool[0],
            start_offset,
            self.address_pool[1],
        )
        checked_serialize_table(
            binary,
            TableType.BYTE_ARRAY_POOL,
            self.byte_array_pool[0],
            start_offset,
            self.byte_array_pool[1],
        )
        return start_offset


    def serialize_common(
        self,
        binary: BinaryData,
        tables: Any,
    ):
        from vm.deserializer import CommonTablesProxy
        tables = CommonTablesProxy(tables)
        self.serialize_module_handles(binary, tables.get_module_handles())
        self.serialize_struct_handles(binary, tables.get_struct_handles())
        self.serialize_function_handles(binary, tables.get_function_handles())
        self.serialize_type_signatures(binary, tables.get_type_signatures())
        self.serialize_function_signatures(binary, tables.get_function_signatures())
        self.serialize_locals_signatures(binary, tables.get_locals_signatures())
        self.serialize_identifiers(binary, tables.get_identifiers())
        self.serialize_addresses(binary, tables.get_address_pool())
        self.serialize_byte_arrays(binary, tables.get_byte_array_pool())


    # Serializes `ModuleHandle` table.
    def serialize_module_handles(
        self,
        binary: BinaryData,
        module_handles: List[ModuleHandle],
    ):
        if module_handles:
            self.table_count += 1
            self.module_handles[0] = check_index_in_binary(binary.__len__())
            for module_handle in module_handles:
                serialize_module_handle(binary, module_handle)

            self.module_handles[1] = checked_calculate_table_size(binary, self.module_handles[0])


    # Serializes `StructHandle` table.
    def serialize_struct_handles(
        self,
        binary: BinaryData,
        struct_handles: List[StructHandle],
    ):
        if struct_handles:
            self.table_count += 1
            self.struct_handles[0] = check_index_in_binary(binary.__len__())
            for struct_handle in struct_handles:
                serialize_struct_handle(binary, struct_handle)

            self.struct_handles[1] = checked_calculate_table_size(binary, self.struct_handles[0])


    # Serializes `FunctionHandle` table.
    def serialize_function_handles(
        self,
        binary: BinaryData,
        function_handles: List[FunctionHandle],
    ):
        if function_handles:
            self.table_count += 1
            self.function_handles[0] = check_index_in_binary(binary.__len__())
            for function_handle in function_handles:
                serialize_function_handle(binary, function_handle)

            self.function_handles[1] =\
                checked_calculate_table_size(binary, self.function_handles[0])


    # Serializes `Identifiers`.
    def serialize_identifiers(
        self,
        binary: BinaryData,
        identifiers: List[Identifier],
    ):
        if identifiers:
            self.table_count += 1
            self.identifiers[0] = check_index_in_binary(binary.__len__())
            for identifier in identifiers:
                # User strings and identifiers use the same serialization.
                serialize_string(binary, identifier)

            self.identifiers[1] = checked_calculate_table_size(binary, self.identifiers[0])


    # Serializes `ByteArrayPool`.
    def serialize_byte_arrays(
        self,
        binary: BinaryData,
        byte_arrays: List[ByteArray],
    ):
        if byte_arrays:
            self.table_count += 1
            self.byte_array_pool[0] = check_index_in_binary(binary.__len__())
            for byte_array in byte_arrays:
                serialize_byte_array(binary, byte_array)

            self.byte_array_pool[1] = checked_calculate_table_size(binary, self.byte_array_pool[0])


    # Serializes `AddressPool`.
    def serialize_addresses(
        self,
        binary: BinaryData,
        addresses: List[Address],
    ):
        if addresses:
            self.table_count += 1
            self.address_pool[0] = check_index_in_binary(binary.__len__())
            for address in addresses:
                serialize_address(binary, address)

            self.address_pool[1] = checked_calculate_table_size(binary, self.address_pool[0])


    # Serializes `TypeSignaturePool` table.
    def serialize_type_signatures(
        self,
        binary: BinaryData,
        signatures: List[TypeSignature],
    ):
        if signatures:
            self.table_count += 1
            self.type_signatures[0] = check_index_in_binary(binary.__len__())
            for signature in signatures:
                serialize_type_signature(binary, signature)

            self.type_signatures[1] = checked_calculate_table_size(binary, self.type_signatures[0])


    # Serializes `FunctionSignaturePool` table.
    def serialize_function_signatures(
        self,
        binary: BinaryData,
        signatures: List[FunctionSignature],
    ):
        if signatures:
            self.table_count += 1
            self.function_signatures[0] = check_index_in_binary(binary.__len__())
            for signature in signatures:
                serialize_function_signature(binary, signature)

            self.function_signatures[1] =\
                checked_calculate_table_size(binary, self.function_signatures[0])


    # Serializes `LocalSignaturePool` table.
    def serialize_locals_signatures(
        self,
        binary: BinaryData,
        signatures: List[LocalsSignature],
    ):
        if signatures:
            self.table_count += 1
            self.locals_signatures[0] = check_index_in_binary(binary.__len__())
            for signature in signatures:
                serialize_locals_signature(binary, signature)

            self.locals_signatures[1] =\
                checked_calculate_table_size(binary, self.locals_signatures[0])


# Holds data to compute the header of a module binary.
@dataclass
class ModuleSerializer:
    common: CommonSerializer
    struct_defs: Tuple[Uint32, Uint32]
    field_defs: Tuple[Uint32, Uint32]
    function_defs: Tuple[Uint32, Uint32]

    @classmethod
    def new(cls, major_version: Uint8, minor_version: Uint8) -> ModuleSerializer:
        return ModuleSerializer(
            common = CommonSerializer.new(major_version, minor_version),
            struct_defs = [0, 0],
            field_defs = [0, 0],
            function_defs = [0, 0],
        )


    def serialize(self, binary: BinaryData, module: CompiledModuleMut):
        self.common.serialize_common(binary, module)
        self.serialize_struct_definitions(binary, module.struct_defs)
        self.serialize_field_definitions(binary, module.field_defs)
        self.serialize_function_definitions(binary, module.function_defs)
        assert self.common.table_count <= 12



    def serialize_header(self, binary: BinaryData):
        start_offset = self.common.serialize_header(binary)
        checked_serialize_table(
            binary,
            TableType.STRUCT_DEFS,
            self.struct_defs[0],
            start_offset,
            self.struct_defs[1],
        )
        checked_serialize_table(
            binary,
            TableType.FIELD_DEFS,
            self.field_defs[0],
            start_offset,
            self.field_defs[1],
        )
        checked_serialize_table(
            binary,
            TableType.FUNCTION_DEFS,
            self.function_defs[0],
            start_offset,
            self.function_defs[1],
        )


    # Serializes `StructDefinition` table.
    def serialize_struct_definitions(
        self,
        binary: BinaryData,
        struct_definitions: List[StructDefinition],
    ):
        if struct_definitions:
            self.common.table_count += 1
            self.struct_defs[0] = check_index_in_binary(binary.__len__())
            for struct_definition in struct_definitions:
                serialize_struct_definition(binary, struct_definition)

            self.struct_defs[1] = checked_calculate_table_size(binary, self.struct_defs[0])


    # Serializes `FieldDefinition` table.
    def serialize_field_definitions(
        self,
        binary: BinaryData,
        field_definitions: List[FieldDefinition],
    ):
        if field_definitions:
            self.common.table_count += 1
            self.field_defs[0] = check_index_in_binary(binary.__len__())
            for field_definition in field_definitions:
                serialize_field_definition(binary, field_definition)

            self.field_defs[1] = checked_calculate_table_size(binary, self.field_defs[0])


    # Serializes `FunctionDefinition` table.
    def serialize_function_definitions(
        self,
        binary: BinaryData,
        function_definitions: List[FunctionDefinition],
    ):
        if function_definitions:
            self.common.table_count += 1
            self.function_defs[0] = check_index_in_binary(binary.__len__())
            for function_definition in function_definitions:
                serialize_function_definition(binary, function_definition)

            self.function_defs[1] = checked_calculate_table_size(binary, self.function_defs[0])



# Holds data to compute the header of a transaction script binary.
@dataclass
class ScriptSerializer:
    common: CommonSerializer
    main: Tuple[Uint32, Uint32]

    @classmethod
    def new(cls, major_version: Uint8, minor_version: Uint8) -> ScriptSerializer:
        return ScriptSerializer(
            common = CommonSerializer.new(major_version, minor_version),
            main = [0, 0],
        )

    def serialize(self, binary: BinaryData, script: CompiledScriptMut):
        self.common.serialize_common(binary, script)
        self.serialize_main(binary, script.main)
        assert self.common.table_count <= 10


    def serialize_header(self, binary: BinaryData):
        start_offset = self.common.serialize_header(binary)
        checked_serialize_table(
            binary,
            TableType.MAIN,
            self.main[0],
            start_offset,
            self.main[1],
        )


    # Serializes the main function.
    def serialize_main(self, binary: BinaryData, main: FunctionDefinition):
        self.common.table_count += 1
        self.main[0] = check_index_in_binary(binary.__len__())
        serialize_function_definition(binary, main)
        self.main[1] = checked_calculate_table_size(binary, self.main[0])

