from __future__ import annotations
from vm.vm_exception import VMException
from vm.errors import *
from vm.file_format import *
from vm.file_format_common import *
from libra.account_address import ADDRESS_LENGTH
from move_core.types.identifier import Identifier
from libra.vm_error import StatusCode, VMStatus
from canoser import Cursor, Uint8, Uint16, Uint32, Uint64, Uint128
from typing import List, Optional, Tuple
import abc

# Table info: table type, offset where the table content starts from, count of bytes for
# the table content.
@dataclass
class Table:
    kind: TableType
    offset: Uint32
    count: Uint32


# Module internal function that manages deserialization of transactions.
def deserialize_compiled_script(binary: bytes) -> CompiledScriptMut:
    binary_len = binary.__len__()
    cursor = Cursor(binary)
    table_count = check_binary(cursor)
    tables: List[Table] = []
    read_tables(cursor, table_count, tables)
    check_tables(tables, cursor.position(), binary_len)

    return build_compiled_script(binary, tables)


# Module internal function that manages deserialization of modules.
def deserialize_compiled_module(binary: bytes) -> CompiledModuleMut:
    binary_len = binary.__len__()
    cursor = Cursor(binary)
    table_count = check_binary(cursor)
    tables: List[Table] = []
    read_tables(cursor, table_count, tables)
    check_tables(tables, cursor.position(), binary_len)

    return build_compiled_module(binary, tables)


# Verifies the correctness of the "static" part of the binary's header.
#
# Returns the offset where the count of tables in the binary.
def check_binary(cursor: Cursor) -> Uint8:
    try:
        magic = cursor.read_bytes(BinaryConstants.LIBRA_MAGIC_SIZE)
        if magic != BinaryConstants.LIBRA_MAGIC:
            raise VMException(VMStatus(StatusCode.BAD_MAGIC))

        major_ver = 1
        minor_ver = 0
        if major_ver != cursor.read_u8():
            raise VMException(VMStatus(StatusCode.UNKNOWN_VERSION))
        if minor_ver != cursor.read_u8():
            raise VMException(VMStatus(StatusCode.UNKNOWN_VERSION))

        return cursor.read_u8()
    except IOError as err:
        raise VMException(VMStatus(StatusCode.MALFORMED))


# Reads all the table headers.
#
# Return a List[Table] that contains all the table headers defined and checked.
def read_tables(
    cursor: Cursor,
    table_count: Uint8,
    tables: List[Table],
):
    for _count in range(table_count):
        tables.append(read_table(cursor))



# Reads a table from a slice at a given offset.
# If a table is not recognized an error is returned.
def read_table(cursor: Cursor) -> Table:
    try:
        kind = cursor.read_u8()
        table_offset = read_Uint32_internal(cursor)
        count = read_Uint32_internal(cursor)
        return Table(TableType.from_u8(kind), table_offset, count)
    except IOError:
        raise VMException(VMStatus(StatusCode.MALFORMED))


# Verify correctness of tables.
#
# Tables cannot have duplicates, must cover the entire blob and must be disjoint.
def check_tables(tables: List[Table], end_tables: Uint64, length: Uint64):
    # there is no real reason to pass a mutable reference but we are sorting next line
    tables.sort(key = lambda x: x.offset)

    current_offset = end_tables
    table_types = set()
    for table in tables:
        offset = table.offset
        if offset != current_offset:
            raise VMException(VMStatus(StatusCode.BAD_HEADER_TABLE))

        if table.count == 0:
            raise VMException(VMStatus(StatusCode.BAD_HEADER_TABLE))

        count = table.count
        checked_offset = Uint64.checked_add(current_offset, count)
        if checked_offset is not None:
            current_offset = checked_offset
        else:
            #TTODO: libra src lack else branch, maybe bug.
            raise VMException(VMStatus(StatusCode.BAD_HEADER_TABLE))
        if current_offset > length:
            raise VMException(VMStatus(StatusCode.BAD_HEADER_TABLE))

        if table.kind in table_types:
            raise VMException(VMStatus(StatusCode.DUPLICATE_TABLE))
        table_types.add(table.kind)

    if current_offset != length:
        raise VMException(VMStatus(StatusCode.BAD_HEADER_TABLE))



#Moved from deserialize.py file
class CommonTables(abc.ABC):

    @abc.abstractmethod
    def get_module_handles(self) -> List[ModuleHandle]:
        pass

    @abc.abstractmethod
    def get_struct_handles(self) -> List[StructHandle]:
        pass

    @abc.abstractmethod
    def get_function_handles(self) -> List[FunctionHandle]:
        pass

    @abc.abstractmethod
    def get_type_signatures(self) -> TypeSignaturePool:
        pass

    @abc.abstractmethod
    def get_function_signatures(self) -> FunctionSignaturePool:
        pass

    @abc.abstractmethod
    def get_locals_signatures(self) -> LocalsSignaturePool:
        pass

    @abc.abstractmethod
    def get_identifiers(self) -> IdentifierPool:
        pass

    @abc.abstractmethod
    def get_byte_array_pool(self) -> bytearrayPool:
        pass

    @abc.abstractmethod
    def get_address_pool(self) -> AddressPool:
        pass


@dataclass
class CommonTablesProxy(CommonTables):
    obj: Any

    def get_module_handles(self) -> List[ModuleHandle]:
        return self.obj.module_handles


    def get_struct_handles(self) -> List[StructHandle]:
        return self.obj.struct_handles


    def get_function_handles(self) -> List[FunctionHandle]:
        return self.obj.function_handles


    def get_type_signatures(self) -> TypeSignaturePool:
        return self.obj.type_signatures


    def get_function_signatures(self) -> FunctionSignaturePool:
        return self.obj.function_signatures


    def get_locals_signatures(self) -> LocalsSignaturePool:
        return self.obj.locals_signatures


    def get_identifiers(self) -> IdentifierPool:
        return self.obj.identifiers


    def get_byte_array_pool(self) -> bytearrayPool:
        return self.obj.byte_array_pool


    def get_address_pool(self) -> AddressPool:
        return self.obj.address_pool



# Builds and returns a `CompiledScriptMut`.
def build_compiled_script(binary: bytes, tables: List[Table]) -> CompiledScriptMut:
    script = CompiledScriptMut.default()
    build_common_tables(binary, tables, script)
    build_script_tables(binary, tables, script)
    return script


# Builds and returns a `CompiledModuleMut`.
def build_compiled_module(binary: bytes, tables: List[Table]) -> CompiledModuleMut:
    module = CompiledModuleMut.default()
    build_common_tables(binary, tables, module)
    build_module_tables(binary, tables, module)
    return module


# Builds the common tables in a compiled unit.
def build_common_tables(
    binary: bytes,
    tables: List[Table],
    common: Any,
):
    common = CommonTablesProxy(common)
    for table in tables:
        if table.kind == TableType.MODULE_HANDLES:
            load_module_handles(binary, table, common.get_module_handles())
        elif table.kind == TableType.STRUCT_HANDLES:
            load_struct_handles(binary, table, common.get_struct_handles())
        elif table.kind == TableType.FUNCTION_HANDLES:
            load_function_handles(binary, table, common.get_function_handles())
        elif table.kind == TableType.ADDRESS_POOL:
            load_address_pool(binary, table, common.get_address_pool())
        elif table.kind == TableType.IDENTIFIERS:
            load_identifiers(binary, table, common.get_identifiers())
        elif table.kind == TableType.BYTE_ARRAY_POOL:
            load_byte_array_pool(binary, table, common.get_byte_array_pool())
        elif table.kind == TableType.TYPE_SIGNATURES:
            load_type_signatures(binary, table, common.get_type_signatures())
        elif table.kind == TableType.FUNCTION_SIGNATURES:
            load_function_signatures(binary, table, common.get_function_signatures())
        elif table.kind == TableType.LOCALS_SIGNATURES:
            load_locals_signatures(binary, table, common.get_locals_signatures())
        elif table.kind == TableType.FUNCTION_DEFS:
            continue
        elif table.kind == TableType.FIELD_DEFS:
            continue
        elif table.kind == TableType.STRUCT_DEFS:
            continue
        elif table.kind == TableType.MAIN:
            continue
        else:
            raise VMException(VMStatus(StatusCode.MALFORMED))


# Builds tables related to a `CompiledModuleMut`.
def build_module_tables(
    binary: bytes,
    tables: List[Table],
    module: CompiledModuleMut,
):
    for table in tables:
        pass
        if table.kind == TableType.STRUCT_DEFS:
            load_struct_defs(binary, table, module.struct_defs)
        elif table.kind == TableType.FIELD_DEFS:
            load_field_defs(binary, table, module.field_defs)
        elif table.kind == TableType.FUNCTION_DEFS:
            load_function_defs(binary, table, module.function_defs)
        elif table.kind == TableType.MAIN:
            raise VMException(VMStatus(StatusCode.MALFORMED))
        elif table.kind in [TableType.MODULE_HANDLES, TableType.STRUCT_HANDLES, \
            TableType.FUNCTION_HANDLES, TableType.ADDRESS_POOL, \
            TableType.IDENTIFIERS, TableType.BYTE_ARRAY_POOL, \
            TableType.TYPE_SIGNATURES, TableType.FUNCTION_SIGNATURES, \
            TableType.LOCALS_SIGNATURES]:
            continue
        else:
            raise VMException(VMStatus(StatusCode.MALFORMED))


# Builds tables related to a `CompiledScriptMut`.
def build_script_tables(
    binary: bytes,
    tables: List[Table],
    script: CompiledScriptMut,
):
    for table in tables:
        if table.kind == TableType.MAIN:
            start: usize = table.offset
            # `check_tables()` ensures that the table indices are in bounds
            assert (start <= usize.max_value - table.count)
            end: usize = start + table.count
            cursor = Cursor(binary[start:end])
            main = load_function_def(cursor)
            script.main = main
        elif table.kind in [TableType.MODULE_HANDLES, TableType.STRUCT_HANDLES, \
            TableType.FUNCTION_HANDLES, TableType.ADDRESS_POOL, \
            TableType.IDENTIFIERS, TableType.BYTE_ARRAY_POOL, \
            TableType.TYPE_SIGNATURES, TableType.FUNCTION_SIGNATURES, \
            TableType.LOCALS_SIGNATURES]:
            continue
        elif table.kind in [TableType.STRUCT_DEFS, TableType.FIELD_DEFS, TableType.FUNCTION_DEFS]:
            raise VMException(VMStatus(StatusCode.MALFORMED))
        else:
            raise VMException(VMStatus(StatusCode.MALFORMED))


# Builds the `ModuleHandle` table.
def load_module_handles(
    binary: bytes,
    table: Table,
    module_handles: List[ModuleHandle],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while True:
        if cursor.position() == table.count:
            break

        address = read_uleb_Uint16_internal(cursor)
        name = read_uleb_Uint16_internal(cursor)
        module_handles.append(ModuleHandle(
            address = AddressPoolIndex(address),
            name = IdentifierIndex(name),
        ))


# Builds the `StructHandle` table.
def load_struct_handles(
    binary: bytes,
    table: Table,
    struct_handles: List[StructHandle],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while True:
        if cursor.position() == table.count:
            break

        module_handle = read_uleb_Uint16_internal(cursor)
        name = read_uleb_Uint16_internal(cursor)
        is_nominal_resource = load_nominal_resource_flag(cursor)
        type_formals = load_kinds(cursor)
        struct_handles.append(StructHandle(
            ModuleHandleIndex(module_handle),
            IdentifierIndex(name),
            is_nominal_resource,
            type_formals,
        ))

# Builds the `FunctionHandle` table.
def load_function_handles(
    binary: bytes,
    table: Table,
    function_handles: List[FunctionHandle],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while True:
        if cursor.position() == table.count:
            break

        module_handle = read_uleb_Uint16_internal(cursor)
        name = read_uleb_Uint16_internal(cursor)
        signature = read_uleb_Uint16_internal(cursor)
        function_handles.append(FunctionHandle(
            module = ModuleHandleIndex(module_handle),
            name = IdentifierIndex(name),
            signature = FunctionSignatureIndex(signature),
        ))


# Builds the `AddressPool`.
def load_address_pool(
    binary: bytes,
    table: Table,
    addresses: AddressPool,
):
    start = table.offset
    if table.count % ADDRESS_LENGTH != 0:
        raise VMException(VMStatus(StatusCode.MALFORMED))

    for _i in range(table.count // ADDRESS_LENGTH):
        end_addr = start + ADDRESS_LENGTH
        if end_addr > len(binary):
            raise VMException(VMStatus(StatusCode.MALFORMED))
        address = binary[start:end_addr]
        start = end_addr
        addresses.append(address)


# Builds the `IdentifierPool`.
def load_identifiers(
    binary: bytes,
    table: Table,
    identifiers: IdentifierPool,
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        size = read_uleb_Uint32_internal(cursor)
        if size > Uint16.max_value:
            raise VMException(VMStatus(StatusCode.MALFORMED))

        try:
            buffer = cursor.read_bytes(size)
            identifiers.append(buffer.decode("utf-8") )
        except:
            raise VMException(VMStatus(StatusCode.MALFORMED))


# Builds the `ByteArrayPool`.
def load_byte_array_pool(
    binary: bytes,
    table: Table,
    byte_arrays: bytearrayPool,
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        size = read_uleb_Uint32_internal(cursor)
        if size > Uint16.max_value:
            raise VMException(VMStatus(StatusCode.MALFORMED))

        try:
            buffer = cursor.read_bytes(size)
            byte_arrays.append(bytearray(buffer))
        except:
            raise VMException(VMStatus(StatusCode.MALFORMED))


# Builds the `TypeSignaturePool`.
def load_type_signatures(
    binary: bytes,
    table: Table,
    type_signatures: TypeSignaturePool,
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        byte = cursor.read_u8()
        if byte != SignatureType.TYPE_SIGNATURE:
            raise VMException(VMStatus(StatusCode.UNEXPECTED_SIGNATURE_TYPE))

        token = load_signature_token(cursor)
        type_signatures.append(TypeSignature(token))


# Builds the `FunctionSignaturePool`.
def load_function_signatures(
    binary: bytes,
    table: Table,
    function_signatures: FunctionSignaturePool,
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        byte = cursor.read_u8()
        if byte != SignatureType.FUNCTION_SIGNATURE:
                raise VMException(VMStatus(StatusCode.UNEXPECTED_SIGNATURE_TYPE))

        # Return signature
        token_count = cursor.read_u8()
        returns_signature: List[SignatureToken] = []
        for _i in range(token_count):
            token = load_signature_token(cursor)
            returns_signature.append(token)

        # Arguments signature
        token_count = cursor.read_u8()
        args_signature: List[SignatureToken] = []
        for _i in range(token_count):
            token = load_signature_token(cursor)
            args_signature.append(token)

        type_formals = load_kinds(cursor)
        function_signatures.append(FunctionSignature(
            returns_signature,
            args_signature,
            type_formals,
        ))


# Builds the `LocalsSignaturePool`.
def load_locals_signatures(
    binary: bytes,
    table: Table,
    locals_signatures: LocalsSignaturePool,
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        byte = cursor.read_u8()
        if byte != SignatureType.LOCAL_SIGNATURE:
            raise VMException(VMStatus(StatusCode.UNEXPECTED_SIGNATURE_TYPE))

        token_count = cursor.read_u8()
        local_signature: List[SignatureToken] = []
        for _i in range(token_count):
            token = load_signature_token(cursor)
            local_signature.append(token)

        locals_signatures.append(LocalsSignature(local_signature))


# Deserializes a `SignatureToken`.
def load_signature_token(cursor: Cursor) -> SignatureToken:
    byte = cursor.read_u8()
    stype = SerializedType.from_u8(byte)
    if stype.is_primitive():
        return SignatureToken(stype)
    elif stype == SerializedType.VECTOR:
        ty = load_signature_token(cursor)
        return SignatureToken(stype, vector_type=ty)
    elif stype == SerializedType.REFERENCE or stype == SerializedType.MUTABLE_REFERENCE:
        ref_token = load_signature_token(cursor)
        return SignatureToken(stype, reference=ref_token)
    elif stype == SerializedType.STRUCT:
        sh_idx = read_uleb_Uint16_internal(cursor)
        types = load_signature_tokens(cursor)
        return SignatureToken(stype, struct=(StructHandleIndex(sh_idx), types))
    elif stype == SerializedType.TYPE_PARAMETER:
        idx = read_uleb_Uint16_internal(cursor)
        return SignatureToken(stype, typeParameter=idx)
    else:
        raise VMException(VMStatus(StatusCode.MALFORMED))


def load_signature_tokens(cursor: Cursor) -> List[SignatureToken]:
    length = read_uleb_Uint16_internal(cursor)
    tokens = []
    for _ in range(length):
        tokens.append(load_signature_token(cursor))
    return tokens


def load_nominal_resource_flag(cursor: Cursor) -> bool:
    byte = cursor.read_u8()
    flag = SerializedNominalResourceFlag.from_u8(byte)
    if flag == SerializedNominalResourceFlag.NOMINAL_RESOURCE:
        return True
    elif flag == SerializedNominalResourceFlag.NORMAL_STRUCT:
        return False
    else:
        raise VMException(VMStatus(StatusCode.MALFORMED))


def load_kind(cursor: Cursor) -> Kind:
    byte = cursor.read_u8()
    kind = SerializedKind.from_u8(byte)
    if kind == SerializedKind.ALL:
        return Kind.All
    elif kind == SerializedKind.UNRESTRICTED:
        return Kind.Unrestricted
    elif kind == SerializedKind.RESOURCE:
        return Kind.Resource
    else:
        raise VMException(VMStatus(StatusCode.MALFORMED))


def load_kinds(cursor: Cursor) -> List[Kind]:
    length = read_uleb_Uint16_internal(cursor)
    kinds = []
    for _ in range(length):
        kinds.append(load_kind(cursor))
    return kinds


# Builds the `StructDefinition` table.
def load_struct_defs(
    binary: bytes,
    table: Table,
    struct_defs: List[StructDefinition],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        struct_handle = read_uleb_Uint16_internal(cursor)
        byte = cursor.read_u8()
        field_information_flag = SerializedNativeStructFlag.from_u8(byte)
        if field_information_flag == SerializedNativeStructFlag.NATIVE:
            field_count = read_uleb_Uint16_internal(cursor)
            if field_count != 0:
                raise VMException(VMStatus(StatusCode.MALFORMED))

            fields_Uint16 = read_uleb_Uint16_internal(cursor)
            if fields_Uint16 != 0:
                raise VMException(VMStatus(StatusCode.MALFORMED))

            field_information = StructFieldInformation.Native()
        elif field_information_flag == SerializedNativeStructFlag.DECLARED:
            field_count = read_uleb_Uint16_internal(cursor)
            fields_Uint16 = read_uleb_Uint16_internal(cursor)
            fields = FieldDefinitionIndex(fields_Uint16)
            field_information = StructFieldInformation.Declared(
                field_count,
                fields,
            )
        else:
            bail("unreachable!")
        struct_defs.append(StructDefinition(
            StructHandleIndex(struct_handle),
            field_information,
        ))


# Builds the `FieldDefinition` table.
def load_field_defs(
    binary: bytes,
    table: Table,
    field_defs: List[FieldDefinition],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        struct_ = read_uleb_Uint16_internal(cursor)
        name = read_uleb_Uint16_internal(cursor)
        signature = read_uleb_Uint16_internal(cursor)
        field_defs.append(FieldDefinition(
            StructHandleIndex(struct_),
            IdentifierIndex(name),
            TypeSignatureIndex(signature),
        ))


# Builds the `FunctionDefinition` table.
def load_function_defs(
    binary: bytes,
    table: Table,
    func_defs: List[FunctionDefinition],
):
    start = table.offset
    end = start + table.count
    cursor = Cursor(binary[start:end])
    while cursor.position() < table.count:
        func_def = load_function_def(cursor)
        func_defs.append(func_def)


# Deserializes a `FunctionDefinition`.
def load_function_def(cursor: Cursor) -> FunctionDefinition:
    function = read_uleb_Uint16_internal(cursor)
    flags = cursor.read_u8()
    acquires_global_resources = load_struct_definition_indices(cursor)
    code_unit = load_code_unit(cursor)
    return FunctionDefinition(
        FunctionHandleIndex(function),
        flags,
        acquires_global_resources,
        code_unit,
    )

# Deserializes a `List[StructDefinitionIndex]`.
def load_struct_definition_indices(
    cursor: Cursor,
) -> List[StructDefinitionIndex]:
    length = cursor.read_u8()
    indices = []
    for _ in range(length):
        indices.append(StructDefinitionIndex(read_uleb_Uint16_internal(cursor)))
    return indices


# Deserializes a `CodeUnit`.
def load_code_unit(cursor: Cursor) -> CodeUnit:
    max_stack_size = read_uleb_Uint16_internal(cursor)
    locals_ = read_uleb_Uint16_internal(cursor)

    code_unit = CodeUnit(
        max_stack_size,
        LocalsSignatureIndex(locals_),
        [],
    )
    load_code(cursor, code_unit.code)
    return code_unit


# Deserializes a code stream (`Bytecode`s).
def load_code(cursor: Cursor, code: List[Bytecode]):
    bytecode_count = read_Uint16_internal(cursor)
    while code.__len__() < bytecode_count:
        byte = cursor.read_u8()
        opcode = Opcodes.from_u8(byte)
        bytecode = Bytecode(opcode)
        if opcode == Opcodes.POP:
            pass
        elif opcode == Opcodes.RET:
            pass
        elif opcode == Opcodes.BR_TRUE or opcode == Opcodes.BR_FALSE or opcode == Opcodes.BRANCH:
            jump = read_Uint16_internal(cursor)
            bytecode.value = jump
        elif opcode == Opcodes.LD_U8:
            value = cursor.read_u8()
            bytecode.value = value
        elif opcode == Opcodes.LD_U64:
            value = read_Uint64_internal(cursor)
            bytecode.value = value
        elif opcode == Opcodes.LD_U128:
            value = read_u128_internal(cursor)
            bytecode.value = value
        elif opcode == Opcodes.CAST_U8 or opcode == Opcodes.CAST_U64 or opcode == Opcodes.CAST_U128:
            pass
        elif opcode == Opcodes.LD_ADDR:
            idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = AddressPoolIndex(idx)
        elif opcode == Opcodes.LD_TRUE or opcode == Opcodes.LD_FALSE:
            pass
        elif opcode == Opcodes.COPY_LOC or\
             opcode == Opcodes.MOVE_LOC or\
             opcode == Opcodes.ST_LOC or\
             opcode == Opcodes.MUT_BORROW_LOC or\
             opcode == Opcodes.IMM_BORROW_LOC:
            idx = cursor.read_u8()
            bytecode.value = idx
        elif opcode == Opcodes.MUT_BORROW_FIELD or\
             opcode == Opcodes.IMM_BORROW_FIELD:
            idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = FieldDefinitionIndex(idx)
        elif opcode == Opcodes.LD_BYTEARRAY:
            idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = ByteArrayPoolIndex(idx)
        elif opcode == Opcodes.CALL:
            idx = read_uleb_Uint16_internal(cursor)
            types_idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = (FunctionHandleIndex(idx), LocalsSignatureIndex(types_idx))
        elif opcode == Opcodes.PACK or\
             opcode == Opcodes.UNPACK:
            idx = read_uleb_Uint16_internal(cursor)
            types_idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = (StructDefinitionIndex(idx), LocalsSignatureIndex(types_idx))
        elif opcode == Opcodes.READ_REF:
            pass
        elif opcode == Opcodes.WRITE_REF:
            pass
        elif opcode == Opcodes.ADD:
            pass
        elif opcode == Opcodes.SUB:
            pass
        elif opcode == Opcodes.MUL:
            pass
        elif opcode == Opcodes.MOD:
            pass
        elif opcode == Opcodes.DIV:
            pass
        elif opcode == Opcodes.BIT_OR:
            pass
        elif opcode == Opcodes.BIT_AND:
            pass
        elif opcode == Opcodes.XOR:
            pass
        elif opcode == Opcodes.SHL:
            pass
        elif opcode == Opcodes.SHR:
            pass
        elif opcode == Opcodes.OR:
            pass
        elif opcode == Opcodes.AND:
            pass
        elif opcode == Opcodes.NOT:
            pass
        elif opcode == Opcodes.EQ:
            pass
        elif opcode == Opcodes.NEQ:
            pass
        elif opcode == Opcodes.LT:
            pass
        elif opcode == Opcodes.GT:
            pass
        elif opcode == Opcodes.LE:
            pass
        elif opcode == Opcodes.GE:
            pass
        elif opcode == Opcodes.ABORT:
            pass
        elif opcode == Opcodes.GET_TXN_GAS_UNIT_PRICE:
            pass
        elif opcode == Opcodes.GET_TXN_MAX_GAS_UNITS:
            pass
        elif opcode == Opcodes.GET_GAS_REMAINING:
            pass
        elif opcode == Opcodes.GET_TXN_SENDER:
            pass
        elif opcode == Opcodes.EXISTS or\
            opcode == Opcodes.MUT_BORROW_GLOBAL or\
            opcode == Opcodes.IMM_BORROW_GLOBAL or\
            opcode == Opcodes.MOVE_FROM or\
            opcode == Opcodes.MOVE_TO:
            idx = read_uleb_Uint16_internal(cursor)
            types_idx = read_uleb_Uint16_internal(cursor)
            bytecode.value = (StructDefinitionIndex(idx), LocalsSignatureIndex(types_idx))
        elif opcode == Opcodes.GET_TXN_SEQUENCE_NUMBER:
            pass
        elif opcode == Opcodes.GET_TXN_PUBLIC_KEY:
            pass
        elif opcode == Opcodes.FREEZE_REF:
            pass
        else:
            bail("unreachable!")
        code.append(bytecode)



def read_uleb_Uint16_internal(cursor: Cursor) -> Uint16:
    return read_uleb128_as_Uint16(cursor)


def read_uleb_Uint32_internal(cursor: Cursor) -> Uint32:
    return read_uleb128_as_Uint32(cursor)


def read_Uint16_internal(cursor: Cursor) -> Uint16:
    return int.from_bytes(cursor.read_bytes(2), byteorder='little', signed=False)


def read_Uint32_internal(cursor: Cursor) -> Uint32:
    return int.from_bytes(cursor.read_bytes(4), byteorder='little', signed=False)


def read_Uint64_internal(cursor: Cursor) -> Uint64:
    return int.from_bytes(cursor.read_bytes(8), byteorder='little', signed=False)


def read_u128_internal(cursor: Cursor) -> Uint128:
    return int.from_bytes(cursor.read_bytes(16), byteorder='little', signed=False)

