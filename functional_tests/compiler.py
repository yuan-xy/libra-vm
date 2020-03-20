from __future__ import annotations
from bytecode_verifier import VerifiedModule
from libra.account_address import Address
from libra_vm.file_format import CompiledModule, CompiledScript
from typing import List, Optional, Callable
from dataclasses import dataclass
import abc


class Compiler(abc.ABC):
    # Compile a transaction script or module.
    @abc.abstractmethod
    def compile(
        self,
        log: Callable[[str], None],
        address: Address,
        input: str,
    ) -> ScriptOrModule:
        bail("unimplemented!")

    # Return the (ordered) list of modules to be used for genesis. If None is returned the staged
    # version of the stdlib is used.
    @abc.abstractmethod
    def stdlib() -> Optional[List[VerifiedModule]]:
        bail("unimplemented!")


@dataclass
class ScriptOrModule:
    script:CompiledScript = None
    module:CompiledModule = None

