from __future__ import annotations
from typing import List, Set, Mapping, Iterable, Optional
from dataclasses import dataclass
import abc
from bytecode_verifier import BlockId, ControlFlowGraph, VMControlFlowGraph
from libra.vm_error import StatusCode, VMStatus
from libra_vm import ModuleAccess, Opcodes
from libra_vm.errors import err_at_offset
from libra_vm.file_format import Bytecode, CompiledModule, FunctionDefinition, StructFieldInformation
from libra_vm.views import FunctionDefinitionView

# This module implements a checker for verifying that basic blocks in the bytecode instruction
# sequence of a function use the evaluation stack in a balanced manner. Every basic block,
# except those that end in Ret (return to caller) opcode, must leave the stack height the
# same as at the beginning of the block. A basic block that ends in Ret opcode must increase
# the stack height by the number of values returned by the function as indicated in its
# signature. Additionally, the stack height must not dip below that at the beginning of the
# block for any basic block.

@dataclass
class StackUsageVerifier:
    module: CompiledModule
    function_definition_view: FunctionDefinitionView#<'a, CompiledModule>

    @classmethod
    def verify(cls,
        module: CompiledModule,
        function_definition: FunctionDefinition,
        cfg: VMControlFlowGraph,
    ) -> List[VMStatus]:
        function_definition_view = FunctionDefinitionView.new(module, function_definition)
        verifier = cls(
            module,
            function_definition_view,
        )

        errors = []
        for block_id in cfg.blocks:
            errors.append(verifier.verify_block(block_id, cfg))

        return errors


    def verify_block(self, block_id: BlockId, cfg: ControlFlowGraph) -> List[VMStatus]:
        code = self.function_definition_view.code().code
        stack_size_increment = 0
        block_start = cfg.block_start(block_id)
        for i in range(block_start, cfg.block_end(block_id)+1):
            (num_pops, num_pushes) = self.instruction_effect(code[i])
            # Check that the stack height is sufficient to accomodate the number
            # of pops this instruction does
            if stack_size_increment < num_pops:
                return [err_at_offset(
                    StatusCode.NEGATIVE_STACK_SIZE_WITHIN_BLOCK,
                    block_start,
                )]

            stack_size_increment -= num_pops
            stack_size_increment += num_pushes


        if stack_size_increment == 0:
            return []
        else:
            return [err_at_offset(
                StatusCode.POSITIVE_STACK_SIZE_AT_BLOCK_END,
                block_start,
            )]


    # The effect of an instruction is a tuple where the first element
    # is the number of pops it does, and the second element is the number
    # of pushes it does
    def instruction_effect(self, instruction: Bytecode) -> Tuple[Uint32, Uint32]:
        if instruction.tag in [
            # Instructions that pop, but don't push
            Opcodes.POP,
            Opcodes.BR_TRUE,
            Opcodes.BR_FALSE,
            Opcodes.ABORT,
            Opcodes.MOVE_TO,
            Opcodes.ST_LOC]:
            return  (1, 0)
        elif instruction.tag in [
            # Instructions that push, but don't pop
            Opcodes.LD_U8,
            Opcodes.LD_U64,
            Opcodes.LD_U128,
            Opcodes.LD_ADDR,
            Opcodes.LD_TRUE,
            Opcodes.LD_FALSE,
            Opcodes.LD_BYTEARRAY,
            Opcodes.COPY_LOC,
            Opcodes.MOVE_LOC,
            Opcodes.MUT_BORROW_LOC,
            Opcodes.IMM_BORROW_LOC,
            Opcodes.GET_TXN_GAS_UNIT_PRICE,
            Opcodes.GET_TXN_MAX_GAS_UNITS,
            Opcodes.GET_GAS_REMAINING,
            Opcodes.GET_TXN_PUBLIC_KEY,
            Opcodes.GET_TXN_SEQUENCE_NUMBER,
            Opcodes.GET_TXN_SENDER]:
            return (0, 1)
        elif instruction.tag in [
            # Instructions that pop and push once
            Opcodes.NOT,
            Opcodes.FREEZE_REF,
            Opcodes.READ_REF,
            Opcodes.EXISTS,
            Opcodes.MUT_BORROW_GLOBAL,
            Opcodes.IMM_BORROW_GLOBAL,
            Opcodes.MUT_BORROW_FIELD,
            Opcodes.IMM_BORROW_FIELD,
            Opcodes.MOVE_FROM,
            Opcodes.CAST_U8,
            Opcodes.CAST_U64,
            Opcodes.CAST_U128]:
            return (1, 1)
        elif instruction.tag in [
            # Binary operations (pop twice and push once)
            Opcodes.ADD,
            Opcodes.SUB,
            Opcodes.MUL,
            Opcodes.MOD,
            Opcodes.DIV,
            Opcodes.BIT_OR,
            Opcodes.BIT_AND,
            Opcodes.XOR,
            Opcodes.SHL,
            Opcodes.SHR,
            Opcodes.OR,
            Opcodes.AND,
            Opcodes.EQ,
            Opcodes.NEQ,
            Opcodes.LT,
            Opcodes.GT,
            Opcodes.LE,
            Opcodes.GE]:
            return (2, 1)
        elif instruction.tag == Opcodes.WRITE_REF:
            # WriteRef pops twice but does not push
            return (2, 0)
        elif instruction.tag == Opcodes.BRANCH:
            # Branch neither pops nor pushes
            return (0, 0)
        elif instruction.tag == Opcodes.RET:
            # Return performs `return_count` pops
            return_count = self.function_definition_view.signature().return_count()
            return (return_count, 0)

        elif instruction.tag == Opcodes.CALL:
            # Call performs `arg_count` pops and `return_count` pushes
            (idx, _) = instruction.value
            function_handle = self.module.function_handle_at(idx)
            signature = self.module.function_signature_at(function_handle.signature)
            arg_count = signature.arg_types.__len__()
            return_count = signature.return_types.__len__()
            return (arg_count, return_count)

        elif instruction.tag == Opcodes.PACK:
            # Pack performs `num_fields` pops and one push
            (idx, _) = instruction.value
            struct_definition = self.module.struct_def_at(idx)
            field_count = struct_definition.field_information.get_field_count()
            # 'Native' here is an error that will be caught by the bytecode verifier later
            return (field_count, 1)

        elif instruction.tag == Opcodes.UNPACK:
            # Unpack performs one pop and `num_fields` pushes
            (idx, _) = instruction.value
            struct_definition = self.module.struct_def_at(idx)
            field_count = struct_definition.field_information.get_field_count()
            return (1, field_count)

        else:
            bail("unreachable!")
