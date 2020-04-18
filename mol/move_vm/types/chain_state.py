from __future__ import annotations
from libra.access_path import AccessPath
from libra.contract_event import ContractEvent
from libra.language_storage import ModuleId
from libra.transaction import TransactionOutput, TransactionStatus
from libra.vm_error import StatusCode, VMStatus
from libra.transaction.write_set import WriteOp, WriteSet
from libra.rustlib import bail
from mol.move_vm.types.loaded_data import StructDef, Type
from mol.move_vm.types.values import GlobalValue, Value
from mol.vm.transaction_metadata import TransactionMetadata
from mol.vm.gas_schedule import GasAlgebra, GasCarrier, GasUnits
from typing import List, Optional, Mapping, Tuple
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
        tryload: bool = False,
    ) -> Optional[GlobalValue]:
        pass

    # Transfer ownership of a resource stored on chain to the VM.
    @abc.abstractmethod
    def move_resource_from_chain(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[GlobalValue]:
        bail("unimplemented!")

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
