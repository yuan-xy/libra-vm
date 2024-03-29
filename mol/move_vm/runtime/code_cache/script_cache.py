from __future__ import annotations
from mol.move_vm.runtime.code_cache.module_cache import load_and_verify_module_id
from mol.move_vm.runtime.interpreter_context import InterpreterContext
from mol.move_vm.runtime.loaded_data import FunctionRef, FunctionReference, LoadedModule

from mol.bytecode_verifier import verify_script_dependencies, VerifiedScript

from libra.hasher import HashValue
from libra.transaction import SCRIPT_HASH_LENGTH
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus

from mol.vm.vm_exception import VMException
from mol.vm.errors import vm_error, Location, VMResult
from mol.vm.file_format import CompiledScript, ScriptAccess
from typing import List, Optional, Mapping
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

# Cache for commonly executed scripts



# The cache for commonly executed scripts. Currently there's no eviction policy, and it maps
# hash of script bytes into `FunctionRef`.
@dataclass
class ScriptCache:
    cmap: Mapping[bytes, FunctionRef] = field(default_factory=dict)


    # Compiles, verifies, caches and resolves `raw_bytes` into a `FunctionRef` that can be
    # executed.
    def cache_script(
        self,
        raw_bytes: bytes,
        context: InterpreterContext,
    ) -> FunctionRef:
        hash_value = HashValue.from_sha3_256(raw_bytes)

        # XXX We may want to put in some negative caching for scripts that fail verification.

        if hash_value in self.cmap:
            logger.debug("[VM] Script cache hit")
            return self.cmap[hash_value]
        else:
            logger.debug("[VM] Script cache miss")
            script = self.__class__.deserialize_and_verify(raw_bytes, context)
            fake_module = script.into_module()
            loaded_module = LoadedModule.new(fake_module)
            ret = FunctionRef.new(loaded_module, CompiledScript.MAIN_INDEX)
            self.cmap[hash_value] = ret
            return ret

    @classmethod
    def deserialize_and_verify(cls,
        raw_bytes: bytes,
        context: InterpreterContext,
    ) -> VerifiedScript:
        try:
            script = CompiledScript.deserialize(raw_bytes)
        except Exception as err:
            logger.warn("[VM] deserializer returned error for script: {}", err)
            raise VMException(vm_error(Location(), StatusCode.CODE_DESERIALIZATION_ERROR)\
                .append_message_with_separator('', err))

        try:
            vscript = VerifiedScript.new(script)
            script = vscript.into_inner()
            # verify dependencies
            script_module = script.self_handle()
            deps = []
            for module in script.module_handles():
                if module == script_module:
                    continue

                module_id = ModuleId(
                    script.address_at(module.address),
                    script.identifier_at(module.name),
                )
                deps.append(load_and_verify_module_id(module_id, context))

            errs = verify_script_dependencies(vscript, deps)
            if not errs:
                return vscript
        except VMException as err:
            errs = err.vm_status

        logger.warning(
            "[VM] bytecode verifier returned errors for script: {}",
            errs
        )
        # If there are errors there should be at least one otherwise there's an internal
        # error in the verifier. We only give back the first error. If the user wants to
        # debug things, they can do that offline.
        raise VMException(errs)
