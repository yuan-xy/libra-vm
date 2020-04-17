from __future__ import annotations
from move_vm.types.identifier import create_access_path, resource_storage_key
from move_vm.runtime.loaded_data import FunctionRef, FunctionReference, LoadedModule
from move_vm.runtime.code_cache import VMModuleCache, ScriptCache
from move_vm.state.data_cache import RemoteCache
from move_vm.runtime.interpreter_context import InterpreterContext
#from move_vm.runtime.interpreter import Interpreter
from move_vm.runtime.loaded_data import FunctionReference, LoadedModule
from bytecode_verifier import VerifiedModule
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from move_core.types.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, StructTag
from libra.transaction import MAX_TRANSACTION_SIZE_IN_BYTES
from libra.vm_error import StatusCode, SubStatus, VMStatus

# from libra_vm.system_module_names import GAS_SCHEDULE_MODULE
# from libra_vm.system_module_names import ACCOUNT_MODULE, ACCOUNT_STRUCT_NAME, EMIT_EVENT_NAME, SAVE_ACCOUNT_NAME

from vm.vm_exception import VMException
from vm.errors import verification_error, vm_error, Location, VMResult, format_str
from vm.file_format import (
    FunctionHandleIndex, FunctionSignature, SignatureToken, StructDefinitionIndex,
    ModuleAccess, CompiledModule, IndexKind
    )
from vm.gas_schedule import CostTable, GAS_SCHEDULE_NAME
from vm.file_format_common import Opcodes
from vm.transaction_metadata import TransactionMetadata
from move_vm.types.loaded_data import StructDef, Type
from move_vm.types.type_context import TypeContext
from move_vm.types.values import Value
from dataclasses import dataclass
from typing import List, Optional, Mapping
import logging

logger = logging.getLogger(__name__)

# An instantiation of the MoveVM.
# `code_cache` is the top level module cache that holds loaded published modules.
# `script_cache` is the cache that stores all the scripts that have previously been invoked.
# `publishing_option` is the publishing option that is set. This can be one of either:
# * Locked, with a whitelist of scripts that the VM is allowed to execute. For scripts that aren't
#   in the whitelist, the VM will just reject it in `verify_transaction`.
# * Custom scripts, which will allow arbitrary valid scripts, but no module publishing
# * Open script and module publishing
@dataclass
class VMRuntime:
    code_cache: VMModuleCache
    script_cache: ScriptCache

    # Create a new VM instance with an Arena allocator to store the modules and a `config` that
    # contains the whitelist that this VM is allowed to execute.
    @classmethod
    def new(cls) -> VMRuntime:
        return cls(VMModuleCache(), ScriptCache())


    def publish_module(
        self,
        module: bytes,
        context: InterpreterContext,
        txn_data: TransactionMetadata,
    ) -> None:
        compiled_module = CompiledModule.deserialize(module)

        # Make sure the module's self address matches the transaction sender. The self address is
        # where the module will actually be published. If we did not check this, the sender could
        # publish a module under anyone's account.
        if compiled_module.address() != txn_data.sender:
            raise VMException(verification_error(
                IndexKind.AddressPool,
                CompiledModule.IMPLEMENTED_MODULE_INDEX,
                StatusCode.MODULE_ADDRESS_DOES_NOT_MATCH_SENDER,
            ))

        # Make sure that there is not already a module with this name published
        # under the transaction sender's account.
        module_id = compiled_module.self_id()
        if context.exists_module(module_id):
            raise VMException(vm_error(
                Location(),
                StatusCode.DUPLICATE_MODULE_NAME,
            ))

        VerifiedModule.new(compiled_module)
        context.publish_module(module_id, module)


    def execute_script(
        self,
        context: InterpreterContext,
        txn_data: TransactionMetadata,
        gas_schedule: CostTable,
        script: bytes,
        args: List[Value],
    ) -> None:
        main = self.script_cache.cache_script(script, context)

        if not verify_actuals(main.signature(), args):
            raise VMException(VMStatus(StatusCode.TYPE_MISMATCH)\
                .with_message("Actual Type Mismatch"))

        from move_vm.runtime.interpreter import Interpreter
        Interpreter.entrypoint(context, self, txn_data, gas_schedule, main, args)


    def execute_function(
        self,
        context: InterpreterContext,
        txn_data: TransactionMetadata,
        gas_schedule: CostTable,
        module: ModuleId,
        function_name: IdentStr,
        args: List[Value],
    ) -> None:
        from move_vm.runtime.interpreter import Interpreter
        Interpreter.execute_function(
            context,
            self,
            txn_data,
            gas_schedule,
            module,
            function_name,
            args,
        )


    def cache_module(self, module: VerifiedModule):
        self.code_cache.cache_module(module)


    def resolve_struct_tag_by_name(
        self,
        module_id: ModuleId,
        name: Identifier,
        context: InterpreterContext,
    ) -> StructTag:
        gas_module = self.code_cache.get_loaded_module(module_id, context)
        gas_struct_def_idx = gas_module.get_struct_def_index(name)
        return resource_storage_key(
            gas_module,
            gas_struct_def_idx,
            [],
        )


    def resolve_struct_def_by_name(
        self,
        module_id: ModuleId,
        name: Identifier,
        context: InterpreterContext,
    ) -> StructDef:
        module = self.code_cache.get_loaded_module(module_id, context)
        struct_idx = module.get_struct_def_index(name)
        return self.code_cache.resolve_struct_def(module, struct_idx, context)


    def resolve_struct_def(
        self,
        module: LoadedModule,
        idx: StructDefinitionIndex,
        type_actuals: List[Type],
        data_view: InterpreterContext,
    ) -> StructDef:
        if not type_actuals:
            return self.code_cache.resolve_struct_def(module, idx, data_view)
        else:
            return self.code_cache.instantiate_struct_def(module, idx, type_actuals, data_view)



    def resolve_function_ref(
        self,
        caller_module: LoadedModule,
        idx: FunctionHandleIndex,
        data_view: InterpreterContext,
    ) -> FunctionRef:
        return self.code_cache.resolve_function_ref(caller_module, idx, data_view)


    def resolve_signature_token(
        self,
        module: LoadedModule,
        tok: SignatureToken,
        type_context: TypeContext,
        data_view: InterpreterContext,
    ) -> Type:
        return self.code_cache.resolve_signature_token(module, tok, type_context, data_view)


    def get_loaded_module(
        self,
        mid: ModuleId,
        data_view: InterpreterContext,
    ) -> LoadedModule:
        return self.code_cache.get_loaded_module(mid, data_view)


# Verify if the transaction arguments match the type signature of the main function.
def verify_actuals(signature: FunctionSignature, args: List[Value]) -> bool:
    if signature.arg_types.__len__() != args.__len__():
        logger.warning(format_str(
            "[VM] different argument length: actuals {}, formals {}",
            args.__len__(),
            signature.arg_types.__len__()
        ))
        return False

    for (ty, arg) in zip(signature.arg_types, args):
        if not arg.is_valid_script_arg(ty):
            logger.warning(format_str(
                "[VM] different argument type: formal {}, actual {}",
                ty, arg
            ))
            return False
    return True

