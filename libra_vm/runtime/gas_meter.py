
# Gas metering logic for the Move VM.

def gas_instr(context, selff, opcode, mem_size):
    context.deduct_gas(selff.gas_schedule.instruction_cost(opcode).total().mul(mem_size))

def gas_const_instr(context, selff, opcode):
    context.deduct_gas(selff.gas_schedule.instruction_cost(opcode).total())

def gas_consume(context, expr):
    context.deduct_gas(expr)

