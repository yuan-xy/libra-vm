from libra_vm.file_format import CompiledModule, CompiledScript
from typing import List, Optional, Mapping
from libra.vm_error import StatusCode, VMStatus
from dataclasses import dataclass

@dataclass
class VerifiedModule:
    v0: CompiledModule

@dataclass
class VerifiedScript:
    v0: CompiledScript


def verify_script_dependencies(
    script: VerifiedScript,
    dependencies:List[VerifiedModule],
) -> List[VMStatus]:
    return []