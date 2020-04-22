from __future__ import annotations
from mol.compiler.bytecode_source_map.source_map import FunctionSourceMap, SourceName
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from mol.bytecode_verifier.control_flow_graph import ControlFlowGraph, VMControlFlowGraph
from mol.move_core.types.identifier import IdentStr
from mol.vm.file_format import (
        ModuleAccess, Bytecode, FieldDefinitionIndex, FunctionDefinition, FunctionDefinitionIndex,
        FunctionSignature, Kind, LocalsSignature, LocalsSignatureIndex, SignatureToken,
        StructDefinition, StructDefinitionIndex, StructFieldInformation, TableIndex, TypeSignature,
    )
from mol.vm.file_format_common import SerializedNativeStructFlag, SerializedType, Opcodes
from typing import List, Optional, Tuple, Mapping
from dataclasses import dataclass
from libra.rustlib import bail, ensure, usize, position, format_str
from canoser import Uint8, Uint16, Uint64, Int64
from itertools import chain
from enum import IntEnum
from copy import deepcopy
from mol.move_ir.types.codespan import Span

Location = Span

# Holds the various options that we support while disassembling code.
@dataclass
class DisassemblerOptions:
    # Only print public functions
    only_public: bool = False

    # Print the bytecode for the instructions within the function.
    print_code: bool = False

    # Print the basic blocks of the bytecode.
    print_basic_blocks: bool = False

    # Print the locals inside each function body.
    print_locals: bool = False


@dataclass
class Disassembler:
    source_mapper: SourceMapping
    # The various options that we can set for disassembly.
    options: DisassemblerOptions


    def get_function_def(
        self,
        function_definition_index: FunctionDefinitionIndex,
    ) -> FunctionDefinition:
        if function_definition_index.v0 >= self.source_mapper.bytecode.function_defs().__len__():
            bail("Invalid function definition index supplied when marking function")

        return self.source_mapper.bytecode.function_def_at(function_definition_index)


    def get_struct_def(
        self,
        struct_definition_index: StructDefinitionIndex,
    ) -> StructDefinition:
        if struct_definition_index.v0 >= self.source_mapper.bytecode.struct_defs().__len__():
            bail("Invalid struct definition index supplied when marking struct")

        return self.source_mapper.bytecode.struct_def_at(struct_definition_index)


    #***************************************************************************
    # Formatting Helpers
    #***************************************************************************

    def name_for_field(self, field_idx: FieldDefinitionIndex) -> str:
        field_def = self.source_mapper.bytecode.field_def_at(field_idx)

        lmd = lambda struct_def: struct_def.struct_handle == field_def.struct_

        struct_def_idx = position(self.source_mapper.bytecode.struct_defs(), lmd)
        if struct_def_idx is None:
            bail("Unable to find struct definition for struct field")

        field_name = self.source_mapper.bytecode.identifier_at(field_def.name)

        struct_def = self.source_mapper.bytecode.struct_def_at(StructDefinitionIndex(struct_def_idx))
        struct_handle = self.source_mapper.bytecode.struct_handle_at(struct_def.struct_handle)
        struct_name = self.source_mapper.bytecode.identifier_at(struct_handle.name)

        return format_str("{}.{}", struct_name, field_name)


    def type_for_field(self, field_idx: FieldDefinitionIndex) -> str:
        field_def = self.source_mapper.bytecode.field_def_at(field_idx)

        lmd = lambda struct_def: struct_def.struct_handle == field_def.struct_
        struct_def_idx = position(self.source_mapper.bytecode.struct_defs(), lmd)
        if struct_def_idx is None:
            bail("Unable to find struct definition for struct field")

        struct_source_info = self.source_mapper.source_map.get_struct_source_map(
            StructDefinitionIndex(struct_def_idx))

        field_type_sig = self.source_mapper.bytecode.type_signature_at(field_def.signature)
        ty = self.disassemble_sig_tok(
            field_type_sig.v0,
            struct_source_info.type_parameters,
        )
        return ty


    def struct_type_info(
        self,
        struct_idx: StructDefinitionIndex,
        types_idx: LocalsSignatureIndex,
    ) -> Tuple[str, str]:
        struct_definition = self.get_struct_def(struct_idx)
        struct_source_map = self.source_mapper.source_map.get_struct_source_map(struct_idx)
        locals_signature = self.source_mapper.bytecode.locals_signature_at(types_idx)

        type_arguments = [self.disassemble_sig_tok(sig_tok, struct_source_map.type_parameters)\
            for sig_tok in locals_signature.v0]

        struct_handle = self.source_mapper.bytecode.struct_handle_at(struct_definition.struct_handle)
        name = self.source_mapper.bytecode.identifier_at(struct_handle.name)
        return (name, self.format_type_params(type_arguments))


    def name_for_local(
        self,
        local_idx: Uint64,
        function_source_map: FunctionSourceMap,
    ) -> str:
        name: SourceName = function_source_map.get_local_name(local_idx)
        if name is None:
            bail(
                "Unable to get local name at index {} while disassembling location-based instruction",
                local_idx
            )
        return name[0]


    def type_for_local(
        self,
        local_idx: Uint64,
        locals_sigs: LocalsSignature,
        function_source_map: FunctionSourceMap,
    ) -> str:
        if local_idx >= len(locals_sigs.v0) or local_idx < 0:
            bail("Unable to get type for local at index {}", local_idx)

        sig_tok = locals_sigs.v0[local_idx]
        return self.disassemble_sig_tok(sig_tok, function_source_map.type_parameters)


    def format_type_params(self, ty_params: List[str]) -> str:
        if not ty_params:
            return ""
        else:
            return format_str("<{}>", ", ".join(ty_params))


    def format_ret_type(self, ty_rets: List[str]) -> str:
        if not ty_rets:
            return ""
        else:
            return format_str(": {}", " * ".join(ty_rets))



    def format_function_body(self, localss: List[str], bytecode: List[str]) -> str:
        if not localss and not bytecode:
            return ""
        else:
            iter1 = [format_str("L{}:\t{}", x, local) for (x, local) in enumerate(localss)]
            body_iter = chain(iter1, bytecode)
            return format_str(" {{\n{}\n}}", "\n".join(body_iter))


    #***************************************************************************
    # Disassemblers
    #***************************************************************************

    # These need to be in the context of a function or a struct definition since type parameters
    # can refer to function/struct type parameters.
    def disassemble_sig_tok(
        self,
        sig_tok: SignatureToken,
        type_param_context: List[SourceName],
    ) -> str:
        if sig_tok.tag.is_primitive():
            return sig_tok.tag.tagname.lower()

        elif sig_tok.tag == SerializedType.STRUCT:
            (struct_handle_idx, instantiation) = sig_tok.struct
            instantiation = [self.disassemble_sig_tok(tok, type_param_context) \
                for tok in instantiation]

            formatted_instantiation = self.format_type_params(instantiation)
            name = self.source_mapper.bytecode.identifier_at(
                self.source_mapper.bytecode.struct_handle_at(struct_handle_idx).name,
            )

            return format_str("{}{}", name, formatted_instantiation)

        elif sig_tok.tag == SerializedType.VECTOR:
            return format_str(
                "vector<{}>",
                self.disassemble_sig_tok(sig_tok.vector_type, type_param_context)
            )
        elif sig_tok.tag == SerializedType.REFERENCE:
            return format_str(
                "&{}",
                self.disassemble_sig_tok(sig_tok.reference, type_param_context)
            )
        elif sig_tok.tag == SerializedType.MUTABLE_REFERENCE:
            return format_str(
                "{}",
                self.disassemble_sig_tok(sig_tok.reference, type_param_context)
            )

        elif sig_tok.tag == SerializedType.TYPE_PARAMETER:
            ty_param_index = sig_tok.typeParameter
            if ty_param_index < 0 or ty_param_index > len(type_param_context):
                bail(
                    "Type parameter index {} out of bounds while disassembling type signature",
                    ty_param_index
                )
            return type_param_context[ty_param_index][0]

        else:
            bail("unreachable!")


    def disassemble_instruction(
        self,
        instruction: Bytecode,
        locals_sigs: LocalsSignature,
        function_source_map: FunctionSourceMap,
        default_location: Location,
    ) -> str:
        tag = instruction.tag
        if tag == Opcodes.LD_ADDR:
            address_idx = instruction.value
            address = self.source_mapper.bytecode.address_at(address_idx)[0:4]
            return format_str("LdAddr[{}]({})", address_idx, address)

        elif tag == Opcodes.LD_BYTEARRAY:
            byte_array_idx = instruction.value
            bytearray = self.source_mapper.bytecode.byte_array_at(byte_array_idx)
            return format_str("LdByteArray[{}]({})", byte_array_idx, bytearray)

        elif tag in[
            Opcodes.COPY_LOC,
            Opcodes.MOVE_LOC,
            Opcodes.ST_LOC,
            Opcodes.MUT_BORROW_LOC,
            Opcodes.IMM_BORROW_LOC,
        ]:
            local_idx = instruction.value
            name = self.name_for_local(local_idx, function_source_map)
            ty = self.type_for_local(local_idx, locals_sigs, function_source_map)
            return format_str("{}[{}]({}: {})", tag.tagname, local_idx, name, ty)

        elif tag in[
            Opcodes.MUT_BORROW_FIELD,
            Opcodes.IMM_BORROW_FIELD,
        ]:
            field_idx = instruction.value
            name = self.name_for_field(field_idx)
            ty = self.type_for_field(field_idx)
            return format_str("{}[{}]({}: {})", tag.tagname, field_idx, name, ty)

        elif tag in[
            Opcodes.PACK,
            Opcodes.UNPACK,
            Opcodes.EXISTS,
            Opcodes.MUT_BORROW_GLOBAL,
            Opcodes.IMM_BORROW_GLOBAL,
            Opcodes.MOVE_FROM,
            Opcodes.MOVE_TO
        ]:
            (struct_idx, types_idx) = instruction.value
            (name, ty_params) = self.struct_type_info(struct_idx, types_idx)
            return format_str("{}[{}]({}{})", tag.tagname, struct_idx, name, ty_params)

        elif tag == Opcodes.CALL:
            method_idx, locals_sig_index = instruction.value
            function_handle = self.source_mapper.bytecode.function_handle_at(method_idx)
            fcall_name = self.source_mapper.bytecode.identifier_at(function_handle.name)

            function_signature = self.source_mapper.bytecode\
                .function_signature_at(function_handle.signature)

            def lambda0(sig_tok):
                return (
                        self.disassemble_sig_tok(
                            sig_tok,
                            function_source_map.type_parameters,
                        ),
                        default_location,
                    )

            ty_params = [lambda0(sig_tok) for sig_tok in  self.source_mapper.bytecode\
                .locals_signature_at(locals_sig_index).v0]

            type_arguments = ", ".join([self.disassemble_sig_tok(sig_tok, ty_params)\
                for sig_tok in function_signature.arg_types])

            type_rets = [self.disassemble_sig_tok(sig_tok, ty_params) for sig_tok \
                in function_signature.return_types]

            return format_str(
                "Call[{}]({}{}({}){})",
                method_idx,
                fcall_name,
                self.format_type_params([s for (s, _) in ty_params]),
                type_arguments,
                self.format_ret_type(type_rets)
            )

        else:
            # All other instructions are OK to be printed using the standard debug print.
            return format_str("{}", instruction)



    def disassemble_bytecode(
        self,
        function_definition_index: FunctionDefinitionIndex,
    ) -> List[str]:
        if not self.options.print_code:
            return [""]

        function_def = self.get_function_def(function_definition_index)
        locals_sigs = self.source_mapper.bytecode.locals_signature_at(function_def.code.locals)
        function_source_map = self.source_mapper.source_map.get_function_source_map(
            function_definition_index)

        decl_location = function_source_map.decl_location

        def lambda0(instruction):
            return self.disassemble_instruction(
                instruction,
                locals_sigs,
                function_source_map,
                decl_location,
            )
        instrs: List[str] = [lambda0(x) for x in function_def.code.code]

        instrs: List[str] = [format_str("\t{}: {}", instr_index, dis_instr) \
            for (instr_index, dis_instr) in enumerate(instrs)]

        if self.options.print_basic_blocks:
            cfg = VMControlFlowGraph.new(function_def.code.code)
            for (block_number, block_id) in enumerate(cfg.blocks.keys()):
                instrs.insert(block_id + block_number, format_str("B{}:", block_number))
            return instrs
        elif self.source_mapper.has_source_code_and_map():
            ret = []
            cur_line_no = 0
            for idx, s in enumerate(instrs):
                line_no = function_source_map.code_map[idx].line_no
                if line_no != cur_line_no:
                    cur_line_no = line_no
                    ret.append("\033[91m>>>" + self.source_mapper.source_code.lines[line_no-1] + "\033[0m")
                ret.append(s)
            return ret
        else:
            return instrs


    def disassemble_type_formals(self,
        source_map_ty_params: List[SourceName],
        kinds: List[Kind],
    ) -> str:
        zipped = zip(source_map_ty_params, kinds)
        ty_params = [format_str("{}: {}", name, kind) for ((name, _), kind) in zipped]
        return self.format_type_params(ty_params)


    def disassemble_locals(
        self,
        function_source_map: FunctionSourceMap,
        function_definition: FunctionDefinition,
        function_signature: FunctionSignature,
    ) -> Tuple[List[str], List[str]]:
        locals_signature = self.source_mapper.bytecode.locals_signature_at(\
            function_definition.code.locals)

        def lambda0(local_idx, name):
            ty = self.type_for_local(local_idx, locals_signature, function_source_map)
            return format_str("{}: {}", name, ty)

        locals_names_tys = [lambda0(local_idx, name) for (local_idx, (name, _)) in \
            enumerate(function_source_map.locls)]

        arg_len = function_signature.arg_types.__len__()
        args = locals_names_tys[0:arg_len]
        locls = locals_names_tys[arg_len:]
        if not self.options.print_locals:
            locls = []

        return (args, locls)


    def disassemble_function_def(
        self,
        function_definition_index: FunctionDefinitionIndex,
    ) -> str:
        function_definition = self.get_function_def(function_definition_index)
        function_handle = self.source_mapper.bytecode.function_handle_at(function_definition.function)
        function_signature = self.source_mapper.bytecode.function_signature_at(function_handle.signature)

        function_source_map = self.source_mapper.source_map.get_function_source_map(function_definition_index)

        if self.options.only_public and not function_definition.is_public():
            return ""

        if function_definition.is_native():
            visibility_modifier = "native "
        elif function_definition.is_public():
            visibility_modifier = "public "
        else:
            visibility_modifier = ""

        ty_params = self.disassemble_type_formals(
            function_source_map.type_parameters,
            function_signature.type_formals,
        )
        name = self.source_mapper.bytecode.identifier_at(function_handle.name)

        ret_type: List[str] = [self.disassemble_sig_tok(x, function_source_map.type_parameters)\
            for x in function_signature.return_types]

        (args, locls) =\
            self.disassemble_locals(function_source_map, function_definition, function_signature)
        bytecode = self.disassemble_bytecode(function_definition_index)

        return format_str(
            "{visibility_modifier}{name}{ty_params}({args}){ret_type}{body}",
            visibility_modifier = visibility_modifier,
            name = name,
            ty_params = ty_params,
            args = ", ".join(args),
            ret_type = self.format_ret_type(ret_type),
            body = self.format_function_body(locls, bytecode),
        )


    # The struct defs will filter out the structs that we print to only be the ones that are
    # defined in the module in question.
    def disassemble_struct_def(self, struct_def_idx: StructDefinitionIndex) -> str:
        struct_definition = self.get_struct_def(struct_def_idx)
        struct_handle = self.source_mapper.bytecode.struct_handle_at(struct_definition.struct_handle)
        struct_source_map = self.source_mapper.source_map.get_struct_source_map(struct_def_idx)

        # field_info: Optional[List[Tuple[IdentStr, TypeSignature]]]
        if struct_definition.field_information.tag == SerializedNativeStructFlag.NATIVE:
            field_info = None
        else:
            field_count = struct_definition.field_information.field_count
            fields = struct_definition.field_information.fields

            def lambda0(i):
                field_definition = self.source_mapper.bytecode.field_def_at(FieldDefinitionIndex(i))
                type_sig = self.source_mapper.bytecode.type_signature_at(field_definition.signature)
                field_name = self.source_mapper.bytecode.identifier_at(field_definition.name)
                return (field_name, type_sig)

            field_info = [lambda0(i) for i in range(fields.v0, fields.v0 + field_count)]

        if field_info is None:
            native = "native "
        else:
            native = ""

        if struct_handle.is_nominal_resource:
            nominal_name = "resource"
        else:
            nominal_name = "struct"

        name = self.source_mapper.bytecode.identifier_at(struct_handle.name)

        ty_params = self.disassemble_type_formals(
            struct_source_map.type_parameters,
            struct_handle.type_formals,
        )
        if field_info is None:
             fields = []
        else:
            def lambda0(name, ty):
                ty_str = self.disassemble_sig_tok(ty.v0, struct_source_map.type_parameters)
                return format_str("{}: {}", name, ty_str)

            fields = [lambda0(name, ty) for (name, ty) in field_info]

        if fields:
            fields[0] = "{\n\t" + fields[0]
            fields[-1] += "\n}"

        return format_str(
            "{native}{nominal_name} {name}{ty_params} {fields}",
            native = native,
            nominal_name = nominal_name,
            name = name,
            ty_params = ty_params,
            fields = ",\n\t".join(fields),
        )


    def disassemble(self) -> str:
        addr = self.source_mapper.source_map.module_name[0]
        name = format_str(
            "{}.{}",
            addr,
            self.source_mapper.source_map.module_name[1]
        )

        struct_defs: List[str] = [self.disassemble_struct_def(StructDefinitionIndex(i)) \
            for i in range(self.source_mapper.bytecode.struct_defs().__len__())]

        function_defs: List[str] = [self.disassemble_function_def(FunctionDefinitionIndex(i)) \
            for i in range(self.source_mapper.bytecode.function_defs().__len__())]

        return format_str(
            "module {name} {{\n{struct_defs}\n\n{function_defs}\n}}",
            name = name,
            struct_defs = "\n".join(struct_defs),
            function_defs = "\n".join(function_defs)
        )

