
# Gas metering logic for the Move VM.

def gas_instr(context, selff, opcode, mem_size):
    if not selff.enable_gas:
        return
    context.deduct_gas(selff.gas_schedule.instruction_cost(opcode).total().mul(mem_size))

def gas_const_instr(context, selff, opcode):
    if not selff.enable_gas:
        return
    context.deduct_gas(selff.gas_schedule.instruction_cost(opcode).total())

def gas_consume(context, expr):
    if not selff.enable_gas:
        return
    context.deduct_gas(expr)

