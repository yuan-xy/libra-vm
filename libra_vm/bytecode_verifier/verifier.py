from libra_vm.file_format import CompiledModule, CompiledScript, ModuleAccess
from typing import List, Optional, Mapping
from libra.vm_error import StatusCode, VMStatus
from dataclasses import dataclass

@dataclass
class VerifiedModule(ModuleAccess):
    v0: CompiledModule

    @classmethod
    def new(cls, value:CompiledModule):
        return cls(value)

    def as_inner(self) -> CompiledModule:
        return self.v0

    def into_inner(self) -> CompiledModule:
        return self.v0

    def as_module(self) -> CompiledModule:
        return self.v0



@dataclass
class VerifiedScript:
    v0: CompiledScript

    @classmethod
    def new(cls, value:CompiledScript):
        return cls(value)

    def as_inner(self) -> CompiledScript:
        return self.v0

    def into_inner(self) -> CompiledScript:
        return self.v0

    def into_module(self) -> VerifiedModule:
        return VerifiedModule(self.into_inner().into_module())


def verify_script_dependencies(
    script: VerifiedScript,
    dependencies:List[VerifiedModule],
) -> List[VMStatus]:
    return []