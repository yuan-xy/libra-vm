from libra.access_path import AccessPath
from libra.contract_event import ContractEvent
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus, SubStatus as sub_status
from mol.move_vm.types.loaded_data import StructDef, Type
from mol.move_vm.types.values import GlobalValue, Value, Struct
from mol.vm.vm_exception import VMException
from mol.vm.errors import *
from mol.vm.gas_schedule import AbstractMemorySize, GasAlgebra, GasCarrier, GasUnits
from typing import List, Optional, Mapping
from dataclasses import dataclass
from copy import deepcopy
import abc
import logging

logger = logging.getLogger(__name__)


# The `InterpreterContext` context trait specifies the mutations that are allowed to the
# `TransactionExecutionContext` within the interpreter.
class InterpreterContext(abc.ABC):
    @abc.abstractmethod
    def move_resource_to(
        self,
        ap: AccessPath,
        sdef: StructDef,
        resource: Struct,
    ) -> None:
        pass

    @abc.abstractmethod
    def move_resource_from(self, ap: AccessPath, sdef: StructDef) -> Value:
        pass

    @abc.abstractmethod
    def resource_exists(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Tuple[bool, AbstractMemorySize]:
        pass

    @abc.abstractmethod
    def borrow_global(self, ap: AccessPath, sdef: StructDef) -> GlobalValue:
        pass

    @abc.abstractmethod
    def push_event(self, event: ContractEvent):
        pass

    @abc.abstractmethod
    def deduct_gas(self, amount: GasUnits) -> None:
        pass

    @abc.abstractmethod
    def remaining_gas(self) -> GasUnits:
        pass

    @abc.abstractmethod
    def exists_module(self, m: ModuleId) -> bool:
        pass

    @abc.abstractmethod
    def load_module(self, module: ModuleId) -> bytes:
        pass

    @abc.abstractmethod
    def publish_module(self, module_id: ModuleId, module: bytes) -> None:
        pass


class InterpreterContextImpl:
    def move_resource_to(
        self,
        ap: AccessPath,
        sdef: StructDef,
        resource: Struct,
    ) -> None:
        # a resource can be written to an AccessPath if the data does not exists or
        # it was deleted (MoveFrom)
        value = self.borrow_resource(ap, deepcopy(sdef), tryload=True)
        can_write = value is None

        if can_write:
            new_root = GlobalValue.new(Value.struct_(resource))
            new_root.mark_dirty()
            self.publish_resource(ap, (sdef, new_root))
        else:
            logger.warning("[VM] Cannot write over existing resource {}", ap)
            raise VMException(vm_error(
                Location(),
                StatusCode.CANNOT_WRITE_EXISTING_RESOURCE,
            ))


    def move_resource_from(self, ap: AccessPath, sdef: StructDef) -> Value:
        global_val = self.move_resource_from_chain(ap, sdef)
        if global_val is not None:
            return Value.struct_(global_val.into_owned_struct())
        else:
            raise VMException(vm_error(Location(), StatusCode.DYNAMIC_REFERENCE_ERROR)\
                    .with_sub_status(sub_status.DRE_GLOBAL_ALREADY_BORROWED))


    def resource_exists(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Tuple[bool, AbstractMemorySize]:
        gref = self.borrow_resource(ap, sdef, tryload=True)
        if gref is not None:
            return (True, gref.size())
        return (False, AbstractMemorySize.new(0))


    def borrow_global(self, ap: AccessPath, sdef: StructDef) -> GlobalValue:
        value = self.borrow_resource(ap, sdef)
        if value is not None:
            return value
        else:
            # TODO: wrong status code
            raise VMException(vm_error(Location.new(), StatusCode.DYNAMIC_REFERENCE_ERROR)\
                    .with_sub_status(sub_status.DRE_GLOBAL_ALREADY_BORROWED))


    def push_event(self, event: ContractEvent):
        self.emit_event(event)

