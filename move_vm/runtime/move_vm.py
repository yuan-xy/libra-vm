from __future__ import annotations
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, StructTag

from move_vm.types.chain_state import ChainState
from move_vm.runtime.loaded_data import LoadedModule
from move_vm.runtime.runtime import VMRuntime
from bytecode_verifier import VerifiedModule

from libra_vm.gas_schedule import CostTable
from libra_vm.file_format_common import Opcodes
from libra_vm.transaction_metadata import TransactionMetadata
from move_vm.types.loaded_data import StructDef
from move_vm.types.values import Value
from dataclasses import dataclass
from typing import List, Optional, Mapping

@dataclass
class MoveVMImpl:
    runtime: VMRuntime


class MoveVM(MoveVMImpl):

    @classmethod
    def new(cls) -> MoveVM:
        return cls(VMRuntime.new())


    def execute_function(
        self,
        module: ModuleId,
        function_name: IdentStr,
        gas_schedule: CostTable,
        chain_state: ChainState,
        txn_data: TransactionMetadata,
        args: List[Value],
    ) -> None:
        self.runtime.execute_function(\
                chain_state, txn_data, gas_schedule, module, function_name, args)


    def execute_script(
        self,
        script: List[Uint8],
        gas_schedule: CostTable,
        chain_state: ChainState,
        txn_data: TransactionMetadata,
        args: List[Value],
    ) -> None:
        self.runtime.execute_script(\
            chain_state, txn_data, gas_schedule, script, args)


    def publish_module(
        self,
        module: List[Uint8],
        chain_state: ChainState,
        txn_data: TransactionMetadata,
    ) -> None:
        self.runtime.publish_module(module, chain_state, txn_data)


    def cache_module(self, module: VerifiedModule):
        self.runtime.cache_module(module)


    def resolve_struct_tag_by_name(
        self,
        module_id: ModuleId,
        name: Identifier,
        chain_state: ChainState,
    ) -> StructTag:
        return self.runtime.resolve_struct_tag_by_name(\
            module_id, name, chain_state)


    def resolve_struct_def_by_name(
        self,
        module_id: ModuleId,
        name: Identifier,
        chain_state: ChainState,
    ) -> StructDef:
        return self.runtime.resolve_struct_def_by_name(\
            module_id, name, chain_state)


    #This is an internal method that is exposed only for tests and cost synthesis.
    #TODO: Figure out a better way to do this.
    def get_loaded_module(
        self,
        mid: ModuleId,
        data_view: InterpreterContext,
    ) -> LoadedModule:
        return self.runtime.get_loaded_module(mid, data_view)


    @classmethod
    def default(cls) -> MoveVM:
        return cls.new()
