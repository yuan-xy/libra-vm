from __future__ import annotations
from libra.vm_error import StatusCode, VMStatus
from mol.vm.errors import verification_error
from mol.vm.file_format import CompiledModule
from mol.vm import ModuleView, IndexKind
from libra.rustlib import usize
from dataclasses import dataclass
from typing import List

# This module implements a checker for verifying that a non-resource class does not
# have resource fields inside it.

@dataclass
class ResourceTransitiveChecker:
    module_view: ModuleView

    @classmethod
    def new(cls, module: CompiledModule) -> ResourceTransitiveChecker:
        return cls(ModuleView.new(module))


    def verify(self) -> List[VMStatus]:
        errors = []
        for (idx, struct_def) in enumerate(self.module_view.structs()):
            if not struct_def.is_nominal_resource():
                fields = struct_def.fields()
                if fields is not None:
                    any_resource_field = False
                    for field in fields:
                        if field.type_signature().contains_nominal_resource(
                        struct_def.type_formals()):
                            any_resource_field = True
                            break

                    if any_resource_field:
                        errors.append(verification_error(
                            IndexKind.StructDefinition,
                            idx,
                            StatusCode.INVALID_RESOURCE_FIELD,
                        ))

        return errors
