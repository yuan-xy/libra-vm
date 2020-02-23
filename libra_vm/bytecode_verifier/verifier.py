from libra_vm.file_format import CompiledModule
from dataclasses import dataclass

@dataclass
class VerifiedModule:
    v0: CompiledModule
