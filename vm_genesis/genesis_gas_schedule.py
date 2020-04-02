from libra_vm.file_format import (
    AddressPoolIndex, ByteArrayPoolIndex, Bytecode, FieldDefinitionIndex, FunctionHandleIndex,
    StructDefinitionIndex, NO_TYPE_ACTUALS, NUMBER_OF_NATIVE_FUNCTIONS
    )
from libra_vm.file_format_common import Opcodes
from libra_vm.gas_schedule import CostTable, GasCost, GAS_SCHEDULE_NAME, MAXIMUM_NUMBER_OF_GAS_UNITS
from move_vm.state.execution_context import TransactionExecutionContext
from move_vm.state.data_cache import RemoteCache
from move_vm.runtime.move_vm import MoveVM
from libra_vm.runtime.system_module_names import GAS_SCHEDULE_MODULE
from move_vm.types.loaded_data import Type
from move_vm.types.values import Value

# This file contains the starting gas schedule published at genesis.


def init_cost_table() -> CostTable:
    cost_map = {
        Opcodes.MOVE_TO: 774,
        Opcodes.GET_TXN_SENDER: 30,
        Opcodes.MOVE_FROM: 917,
        Opcodes.BR_TRUE: 31,
        Opcodes.WRITE_REF:65,
        Opcodes.MUL: 41,
        Opcodes.MOVE_LOC:41,
        Opcodes.AND:49,
        Opcodes.GET_TXN_PUBLIC_KEY:41,
        Opcodes.POP:27,
        Opcodes.BIT_AND:44,
        Opcodes.READ_REF:51,
        Opcodes.SUB:44,
        Opcodes.MUT_BORROW_FIELD:58,
        Opcodes.IMM_BORROW_FIELD:58,
        Opcodes.ADD:45,
        Opcodes.COPY_LOC:41,
        Opcodes.ST_LOC:28,
        Opcodes.RET:28,
        Opcodes.LT:49,
        Opcodes.LD_U8:29,
        Opcodes.LD_U64:29,
        Opcodes.LD_U128:29,
        Opcodes.CAST_U8:29,
        Opcodes.CAST_U64:29,
        Opcodes.CAST_U128:29,
        Opcodes.ABORT:39,
        Opcodes.MUT_BORROW_LOC:45,
        Opcodes.IMM_BORROW_LOC:45,
        Opcodes.LD_ADDR:36,
        Opcodes.GE:46,
        Opcodes.XOR:46,
        Opcodes.SHL:46,
        Opcodes.SHR:46,
        Opcodes.NEQ:51,
        Opcodes.NOT:35,
        Opcodes.CALL:197,
        Opcodes.LE:47,
        Opcodes.BRANCH:10,
        Opcodes.UNPACK:94,
        Opcodes.OR:43,
        Opcodes.LD_FALSE:30,
        Opcodes.LD_TRUE:29,
        Opcodes.GET_TXN_GAS_UNIT_PRICE:29,
        Opcodes.MOD:42,
        Opcodes.BR_FALSE:29,
        Opcodes.EXISTS:856,
        Opcodes.GET_GAS_REMAINING:32,
        Opcodes.BIT_OR:45,
        Opcodes.GET_TXN_MAX_GAS_UNITS:34,
        Opcodes.GET_TXN_SEQUENCE_NUMBER:29,
        Opcodes.FREEZE_REF:10,
        Opcodes.MUT_BORROW_GLOBAL:929,
        Opcodes.IMM_BORROW_GLOBAL:929,
        Opcodes.DIV:41,
        Opcodes.EQ:48,
        Opcodes.LD_BYTEARRAY:56,
        Opcodes.GT:46,
        Opcodes.PACK:73
    }

    def lambda1(opcode: Opcodes):
        return (Bytecode.default(opcode), GasCost.new(cost_map[opcode], 1))
    instrs = [lambda1(x) for x in list(Opcodes)]

    # instrs = []
    # for opcode, v in cost_map.items():
    #     item = (Bytecode.default(opcode), GasCost.new(v, 1))
    #     instrs.append(item)

    assert len(instrs) == Bytecode.NUM_INSTRUCTIONS

    # TODO Zero for now, this is going to be filled in later
    native_table = [GasCost.new(0, 0) for _x in range(NUMBER_OF_NATIVE_FUNCTIONS)]
    return CostTable.new(instrs, native_table)

def init_gas() -> bytes:
    cost_table = init_cost_table()
    return cost_table.serialize()

INITIAL_GAS_SCHEDULE = init_gas()

def initial_gas_schedule(move_vm: MoveVM, data_view: RemoteCache) -> Value:
    # struct_def = move_vm.resolve_struct_def_by_name(
    #         GAS_SCHEDULE_MODULE,
    #         GAS_SCHEDULE_NAME,
    #         TransactionExecutionContext.new(MAXIMUM_NUMBER_OF_GAS_UNITS, data_view),
    #     )
    # return Value.simple_deserialize(INITIAL_GAS_SCHEDULE, Type('Struct', struct_def))
    return Value.gas_costtable_to_value(init_cost_table())

