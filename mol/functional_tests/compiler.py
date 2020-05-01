from __future__ import annotations
from mol.bytecode_verifier import VerifiedModule
from mol.compiler.bytecode_source_map.source_map import SourceMap
from mol.compiler.bytecode_source_map.mapping import SourceMapping
from libra.account_address import Address
from libra.rustlib import bail
from mol.vm.file_format import CompiledModule, CompiledScript
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
    def stdlib(self) -> Optional[List[VerifiedModule]]:
        bail("unimplemented!")


@dataclass
class ScriptOrModule:
    script:CompiledScript = None
    module:CompiledModule = None
    source_map: SourceMap = None
    source_mapping: SourceMapping = None

