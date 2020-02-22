from __future__ import annotations
from libra_vm.runtime.counters import *
from libra_vm.runtime.data_cache import RemoteCache, TransactionDataCache
from libra.access_path import AccessPath
from libra.contract_event import ContractEvent
from libra.language_storage import ModuleId
from libra.transaction import TransactionOutput, TransactionStatus
from libra.vm_error import StatusCode, VMStatus
from libra.transaction.write_set import WriteOp, WriteSet
from libra_vm.runtime_types.loaded_data import StructDef, Type
from libra_vm.runtime_types.values import GlobalValue, Value
from libra_vm.transaction_metadata import TransactionMetadata
from libra_vm.gas_schedule import GasAlgebra, GasCarrier, GasUnits
from typing import List, Optional, Mapping
from dataclasses import dataclass
import abc


# Trait that describes what Move bytecode runtime expects from the Libra blockchain.
class ChainState(abc.ABC):
    @abc.abstractmethod
    def deduct_gas(self, amount: GasUnits) -> None:
        pass

    @abc.abstractmethod
    def remaining_gas(self) -> GasUnits:
        pass

    # ---
    # StateStore operations
    # ---

    # An alternative for these APIs might look like:
    #
    #   def read_data(self, ap: &AccessPath) -> VMbytes
    #   def write_data(self, ap: &AccessPath, data: bytes) -> VM()
    #
    # However, this would make the Move VM responsible for deserialization -- in particular,
    # caching deserialized results leads to a big performance improvement. But this directly
    # conflicts with the goal of the Move VM to be as stateless as possible. Hence the burden of
    # deserialization (and caching) is placed on the implementer of this trait.

    # Get the serialized format of a `CompiledModule` from chain given a `ModuleId`.
    @abc.abstractmethod
    def load_module(self, module: ModuleId) -> bytes:
        pass

    # Get a reference to a resource stored on chain.
    @abc.abstractmethod
    def borrow_resource(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[GlobalValue]:
        pass

    # Transfer ownership of a resource stored on chain to the VM.
    @abc.abstractmethod
    def move_resource_from(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[GlobalValue]:
        pass

    # Publish a module to be stored on chain.
    @abc.abstractmethod
    def publish_module(self, module_id: ModuleId, module: bytes) -> None:
        pass

    # Publish a resource to be stored on chain.
    @abc.abstractmethod
    def publish_resource(self, ap: AccessPath, g: Tuple[StructDef, GlobalValue]) -> None:
        pass

    # Check if this module exists on chain.
    # TODO: Can we get rid of this api with the loader refactor
    @abc.abstractmethod
    def exists_module(self, key: ModuleId) -> bool:
        pass

    # ---
    # EventStore operations
    # ---

    # Emit an event to the EventStore
    @abc.abstractmethod
    def emit_event(self, event: ContractEvent):
        pass


# A TransactionExecutionContext holds the mutable data that needs to be persisted from one
# section of the transaction flow to another. Because of this, this is the _only_ data that can
# both be mutated, and persist between interpretation instances.
@dataclass
class TransactionExecutionContext(ChainState):
    # Gas metering to track cost of execution.
    gas_left: GasUnits
    # List of events "fired" during the course of an execution.
    event_data: List[ContractEvent]
    # Data store
    data_view: TransactionDataCache


    @classmethod
    def new(cls, gas_left: GasUnits, data_cache: RemoteCache) -> TransactionExecutionContext:
        return TransactionExecutionContext(gas_left, [], data_cache)

    # Clear all the writes local to this execution.
    def clear(self):
        self.data_view.clear()
        self.event_data.clear()


    # Return the list of events emitted during execution.
    def events(self) -> List[ContractEvent]:
        return self.event_data


    # Generate a `WriteSet` as a result of an execution.
    def make_write_set(self) -> WriteSet:
        return self.data_view.make_write_set()


    def get_transaction_output(
        self,
        txn_data: TransactionMetadata,
        status: VMStatus,
    ) -> TransactionOutput:
        gas_used: Uint64 = txn_data \
            .max_gas_amount()       \
            .sub(self.gas_left())   \
            .mul(txn_data.gas_unit_price()) \
            .get()
        write_set = self.make_write_set()
        # record_stats!(observe | TXN_TOTAL_GAS_USAGE | gas_used)
        return TransactionOutput(
            write_set,
            self.events,
            gas_used,
            TransactionStatus(TransactionStatus.Keep, status),
        )


    def deduct_gas(self, amount: GasUnits):
        if self.gas_left.app(amount, lambda curr_gas, gas_amt: curr_gas >= gas_amt):
            self.gas_left = self.gas_left.sub(amount)
        else:
            # Zero out the internal gas state
            self.gas_left = GasUnits.new(0)
            raise VMException(VMStatus(StatusCode.OUT_OF_GAS))


    def remaining_gas(self) -> GasUnits:
        return self.gas_left


    def borrow_resource(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[GlobalValue]:
        map_entry = self.data_view.load_data(ap, sdef)
        return map_entry[1]


    def move_resource_from(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[GlobalValue]:
        map_entry = self.data_view.load_data_then_move(ap, sdef)
        # .take() means that the entry is removed from the data map -- this marks the
        # access path for deletion.
        return map_entry[1]


    def load_module(self, module: ModuleId) -> bytes:
        return self.data_view.load_module(module)


    def publish_module(self, module_id: ModuleId, module: bytes):
        self.data_view.publish_module(module_id, module)


    def publish_resource(self, ap: AccessPath, g: Tuple[StructDef, GlobalValue]):
        self.data_view.publish_resource(ap, g)


    def exists_module(self, key: ModuleId) -> bool:
        return self.data_view.exists_module(key)


    def emit_event(self, event: ContractEvent):
        self.event_data.append(event)


class SystemExecutionContext(TransactionExecutionContext):

    @classmethod
    def new(data_cache: RemoteCache, gas_left: GasUnits) -> SystemExecutionContext:
        return SystemExecutionContext(gas_left, [], data_cache)

    def deduct_gas(self, _amount: GasUnits):
        pass

    def From(ctx: TransactionExecutionContext) -> SystemExecutionContext:
        return SystemExecutionContext(ctx.gas_left, ctx.event_data, ctx.data_view)
