from __future__ import annotations
from vm.file_format import (
    AddressPoolIndex, ByteArrayPoolIndex, Bytecode, FieldDefinitionIndex, FunctionHandleIndex,
    StructDefinitionIndex, NO_TYPE_ACTUALS, NUMBER_OF_NATIVE_FUNCTIONS
    )
from vm.file_format_common import Opcodes
from move_core.types.identifier import Identifier
from libra.transaction import MAX_TRANSACTION_SIZE_IN_BYTES
from libra.rustlib import ensure, bail
from canoser import Uint64, Uint8, Struct
from canoser.base import Base
from enum import IntEnum
from dataclasses import dataclass
from typing import List, TypeVar
import abc

# This module lays out the basic abstract costing schedule for bytecode instructions.
#
# It is important to note that the cost schedule defined in this file does not track hashing
# operations or other native operations; the cost of each native operation will be returned by the
# native function itself.


# The underlying carrier for gas-related units and costs. Data with this type should not be
# manipulated directly, but instead be manipulated using the newtype wrappers defined around
# them and the functions defined in the `GasAlgebra` trait.
GasCarrier = Uint64

def add_lambda(x1, x2):
    return x1+x2

def sub_lambda(x1, x2):
    return x1-x2

def mul_lambda(x1, x2):
    return x1 * x2

def div_lambda(x1, x2):
    return x1 // x2

# A trait encoding the operations permitted on the underlying carrier for the gas unit, and how
# other gas-related units can interact with other units -- operations can only be performed
# across units with the same underlying carrier (i.e. as long as the underlying data is
# the same).
class GasAlgebra(abc.ABC):
    # Project a value into the gas algebra.
    @classmethod
    @abc.abstractmethod
    def new(cls, carrier: GasCarrier) -> GasAlgebra:
        bail("unimplemented!")

    # Get the carrier.
    @abc.abstractmethod
    def get(self) -> GasCarrier:
        bail("unimplemented!")

    # Map a function `f` of one argument over the underlying data.
    def map(self, f: Callable[[GasCarrier], GasCarrier]) -> GasAlgebra:
        return self.__class__.new(f(self.get()))


    # Map a function `f` of two arguments over the underlying carrier. Note that this function
    # can take two different implementations of the trait -- one for `self` the other for the
    # second argument. But, we enforce that they have the same underlying carrier.
    def map2(
        self,
        other: GasAlgebra,
        f: Callable[[GasCarrier, GasCarrier], GasCarrier],
    ) -> GasAlgebra:
        ret = f(self.get(), other.get())
        return self.__class__.new(ret)


    T = TypeVar('T')
    # Apply a function `f` of two arguments to the carrier. Since `f` is not an endomophism, we
    # return the resulting value, as opposed to the result wrapped up in ourselves.
    def app(
        self,
        other: GasAlgebra,
        f: Callable[[GasCarrier, GasCarrier], T],
    ) -> T:
        return f(self.get(), other.get())


    # We allow casting between GasAlgebras as long as they have the same underlying carrier --
    # i.e. they use the same type to store the underlying value.
    def unitary_cast(self, clazz) -> GasAlgebra:
        return clazz.new(self.get())


    # Add the two `GasAlgebra`s together.
    def add(self, right: GasAlgebra) -> GasAlgebra:
        return self.map2(right, add_lambda)


    # Subtract one `GasAlgebra` from the other.
    def sub(self, right: GasAlgebra) -> GasAlgebra:
        return self.map2(right, sub_lambda)


    # Multiply two `GasAlgebra`s together.
    def mul(self, right: GasAlgebra) -> GasAlgebra:
        return self.map2(right, mul_lambda)


    # Divide one `GasAlgebra` by the other.
    def div(self, right: GasAlgebra) -> GasAlgebra:
        return self.map2(right, div_lambda)


# We would really like to be able to implement the standard arithmetic traits over the GasAlgebra
# trait, but that isn't possible.
@dataclass
class GasAlgebraBase(GasAlgebra):
    v0: GasCarrier

    @classmethod
    def new(cls, c: GasCarrier) -> GasAlgebra:
        return cls(c)

    def get(self) -> GasCarrier:
        return self.v0

#A newtype wrapper that represents the (abstract) memory size that the instruciton will take up.
class AbstractMemorySize(GasAlgebraBase):
    pass

#A newtype wrapper around the underlying carrier for the gas cost
class GasUnits(GasAlgebraBase, Base):
    @classmethod
    def encode(cls, value):
        return GasCarrier.encode(value.v0)

    @classmethod
    def decode(cls, cursor):
        v0 = GasCarrier.decode(cursor)
        return cls(v0)

    @classmethod
    def check_value(cls, value):
        GasCarrier.check_value(value.v0)

    def to_json_serializable(self):
        return GasCarrier.to_json_serializable(self.v0)


#A newtype wrapper around the gas price for each unit of gas consumed
class GasPrice(GasAlgebraBase):
    pass


# The cost per-byte written to global storage.
# TODO: Fill this in with a proper number once it's determined.
GLOBAL_MEMORY_PER_BYTE_COST = GasUnits.new(8)

# The cost per-byte written to storage.
# TODO: Fill this in with a proper number once it's determined.
GLOBAL_MEMORY_PER_BYTE_WRITE_COST = GasUnits.new(8)

# The maximum size representable by AbstractMemorySize
MAX_ABSTRACT_MEMORY_SIZE = AbstractMemorySize.new(Uint64.max_value)

# The units of gas that should be charged per byte for every transaction.
INTRINSIC_GAS_PER_BYTE= GasUnits.new(8)

# The minimum gas price that a transaction can be submitted with.
MIN_PRICE_PER_GAS_UNIT = GasPrice.new(0)

# The maximum gas unit price that a transaction can be submitted with.
MAX_PRICE_PER_GAS_UNIT = GasPrice.new(10_000)

# 1 nanosecond should equal one unit of computational gas. We bound the maximum
# computational time of any given transaction at 10 milliseconds. We want this number and
# `MAX_PRICE_PER_GAS_UNIT` to always satisfy the inequality that
#         MAXIMUM_NUMBER_OF_GAS_UNITS * MAX_PRICE_PER_GAS_UNIT < min(Uint64.MAX, GasUnits<GasCarrier>.MAX)
MAXIMUM_NUMBER_OF_GAS_UNITS = GasUnits.new(1_000_000)

# We charge one unit of gas per-byte for the first 600 bytes
MIN_TRANSACTION_GAS_UNITS = GasUnits.new(600)

# The word size that we charge by
WORD_SIZE = AbstractMemorySize.new(8)

# The size in words for a non-string or address constant on the stack
CONST_SIZE = AbstractMemorySize.new(1)

# The size in words for a reference on the stack
REFERENCE_SIZE = AbstractMemorySize.new(8)

# The size of a struct in words
STRUCT_SIZE = AbstractMemorySize.new(2)

# For V1 all accounts will be 32 words
DEFAULT_ACCOUNT_SIZE = AbstractMemorySize.new(32)

# Any transaction over this size will be charged `INTRINSIC_GAS_PER_BYTE` per byte
LARGE_TRANSACTION_CUTOFF = AbstractMemorySize.new(600)

GAS_SCHEDULE_NAME = "T"

# The encoding of the instruction is the serialized form of it, but disregarding the
# serialization of the instruction's argument(s).
def instruction_key(instruction: Bytecode) -> Uint8:
    return instruction.tag



# The  `GasCost` tracks:
# - instruction cost: how much time/computational power is needed to perform the instruction
# - memory cost: how much memory is required for the instruction, and storage overhead
class GasCost(Struct):
    _fields = [
        ('instruction_gas', GasUnits),
        ('memory_gas', GasUnits)
    ]


    @classmethod
    def new(cls, instr_gas: GasCarrier, mem_gas: GasCarrier) -> GasCost:
        return GasCost(
            instruction_gas = GasUnits.new(instr_gas),
            memory_gas = GasUnits.new(mem_gas),
        )

    # Take a GasCost from our gas schedule and convert it to a total gas charge in `GasUnits`.
    #
    # This is used internally for converting from a `GasCost` which is a triple of numbers
    # represeing instruction, stack, and memory consumption into a number of `GasUnits`.
    def total(self) -> GasUnits:
        return self.instruction_gas.add(self.memory_gas)


# The cost tables, keyed by the serialized form of the bytecode instruction.  We use the
# serialized form as opposed to the instruction enum itself as the key since this will be the
# on-chain representation of bytecode instructions in the future.
class CostTable(Struct):
    _fields = [
        ('instruction_table', [GasCost]),
        ('native_table', [GasCost])
    ]

    @classmethod
    def new(cls, instrs: List[Tuple[Bytecode, GasCost]], native_table: List[GasCost]):
        instrs.sort(key = lambda x: instruction_key(x[0]))

        debug_assertions = True
        if debug_assertions:
            instructions_covered = 0
            for (index, (instr, _)) in enumerate(instrs):
                key = instruction_key(instr)
                if index == (key - 1):
                    instructions_covered += 1

            ensure(
                instructions_covered == Bytecode.NUM_INSTRUCTIONS,
                "all instructions must be in the cost table"
            )

        instruction_table = [cost for (_, cost) in instrs]
        return cls(
            instruction_table,
            native_table,
        )


    def instruction_cost(self, instr_index: Uint8) -> GasCost:
        return self.instruction_table[instr_index - 1]


    def native_cost(self, native_index: NativeCostIndex) -> GasCost:
        return self.native_table[native_index]


    def get_gas(
        self,
        instr: Bytecode,
        size_provider: AbstractMemorySize,
    ) -> GasCost:
        # NB: instruction keys are 1-indexed. This means that their location in the cost array
        # will be the key - 1.
        key = instruction_key(instr)
        cost = self.instruction_table.get(key - 1)
        assert coset is not None
        good_cost = cost
        return GasCost(
            instruction_gas = good_cost.instruction_gas.map2(size_provider, mul_lambda),
            memory_gas = good_cost.memory_gas.map2(size_provider, mul_lambda),
        )


    # Only used for genesis, cost synthesis (for now) and for tests where we need a cost table and
    # don't have a genesis storage state.
    @classmethod
    def zero(cls) -> CostTable:
        # The actual costs for the instructions in this table _DO NOT MATTER_. This is only used
        # for genesis, cost synthesis, and testing, and for these cases we don't need to worry
        # about the actual gas for instructions.  The only thing we care about is having an entry
        # in the gas schedule for each instruction.
        instrs = [(Bytecode.default(opcode), GasCost.new(0, 0)) for opcode in list(Opcodes)]
        native_table = [GasCost.new(0, 0) for _x in range(NUMBER_OF_NATIVE_FUNCTIONS)]
        return CostTable.new(instrs, native_table)


# Computes the number of words rounded up
def words_in(size: AbstractMemorySize) -> AbstractMemorySize:
    assert(size.get() <= MAX_ABSTRACT_MEMORY_SIZE.get() - (WORD_SIZE.get() + 1))
    def fun(size, word_size):
        # static invariant
        assert(word_size > 0)
        # follows from the precondition
        assert(size <= Uint64.max_value - word_size)
        return (size + (word_size - 1)) // word_size

    # round-up div truncate
    return size.map2(WORD_SIZE, fun)


# Calculate the intrinsic gas for the transaction based upon its size in bytes/words.
def calculate_intrinsic_gas(
    transaction_size: AbstractMemorySize,
) -> GasUnits:
    assert(transaction_size.get() <= MAX_TRANSACTION_SIZE_IN_BYTES)
    min_transaction_fee = MIN_TRANSACTION_GAS_UNITS

    if transaction_size.get() > LARGE_TRANSACTION_CUTOFF.get():
        excess = words_in(transaction_size.sub(LARGE_TRANSACTION_CUTOFF))
        return min_transaction_fee.add(INTRINSIC_GAS_PER_BYTE.mul(excess))
    else:
        return min_transaction_fee.unitary_cast(GasUnits)



class NativeCostIndex(IntEnum):
    SHA2_256 = 0,
    SHA3_256 = 1,
    ED25519_VERIFY = 2,
    ED25519_THRESHOLD_VERIFY = 3,
    ADDRESS_TO_BYTES = 4,
    U64_TO_BYTES = 5,
    BYTEARRAY_CONCAT = 6,
    LENGTH = 7,
    EMPTY = 8,
    BORROW = 9,
    BORROW_MUT = 10,
    PUSH_BACK = 11,
    POP_BACK = 12,
    DESTROY_EMPTY = 13,
    SWAP = 14,
    WRITE_TO_EVENT_STORE = 15,
    SAVE_ACCOUNT = 16,

