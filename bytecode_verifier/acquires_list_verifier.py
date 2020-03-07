from libra.vm_error import StatusCode, VMStatus
from libra_vm import ModuleAccess, Opcodes
from libra_vm.errors import err_at_offset
from libra_vm.file_format import Bytecode, CompiledModule, FunctionDefinition, StructDefinitionIndex
from libra_vm.views import FunctionDefinitionView, ModuleView, StructDefinitionView, ViewInternals
from libra.rustlib import usize
from typing import List, Any, Optional, Mapping, Set
from dataclasses import dataclass
from copy import deepcopy

# This module implements a checker for verifying properties about the acquires list on function
# definitions. Function definitions must annotate the global resources (declared in that module)
# accesssed by `BorrowGlobal`, `MoveFrom`, and any transitive function calls
# The list of acquired resources (stored in `FunctionDefinition`'s `acquires_global_resources`
# field) must have:
# - No duplicate resources (checked by `check_duplication`)
# - No missing resources (any resource acquired must be present)
# - No additional resources (no extraneous resources not actually acquired)

@dataclass
class AcquiresVerifier:
    module_view: ModuleView
    annotated_acquires: Set #BTreeSet<StructDefinitionIndex>,
    actual_acquires: Set #<StructDefinitionIndex>,
    errors: List[VMStatus]

    @classmethod
    def verify(cls,
        module: CompiledModule,
        function_definition: FunctionDefinition,
    ) -> List[VMStatus]:
        annotated_acquires = deepcopy(function_definition.acquires_global_resources)

        verifier = cls(
            module_view = ModuleView.new(module),
            annotated_acquires = annotated_acquires,
            actual_acquires = set(),
            errors = [],
        )

        function_definition_view = FunctionDefinitionView.new(module, function_definition)
        for (offset, instruction) in enumerate(function_definition_view.code().code):
            verifier.verify_instruction(instruction, offset)


        for annotation in verifier.annotated_acquires:
            if annotation not in verifier.actual_acquires:
                verifier.errors.append(VMStatus(
                    StatusCode.EXTRANEOUS_ACQUIRES_RESOURCE_ANNOTATION_ERROR,
                ))


            struct_def = module.struct_defs()[annotation.v0]
            struct_def_view = StructDefinitionView.new(module, struct_def)
            if not struct_def_view.is_nominal_resource():
                verifier.errors.append(VMStatus(
                    StatusCode.INVALID_ACQUIRES_RESOURCE_ANNOTATION_ERROR,
                ))

        return verifier.errors


    def verify_instruction(self, instruction: Bytecode, offset: usize):
        if instruction.tag == Opcodes.CALL:
            (idx, _) = instruction.value
            function_handle = self.module_view.as_inner().function_handle_at(idx)
            function_acquired_resources = self.module_view\
                .function_acquired_resources(function_handle)

            for x in function_acquired_resources:
                if x not in self.annotated_acquires:
                    self.errors.append(err_at_offset(
                        StatusCode.MISSING_ACQUIRES_RESOURCE_ANNOTATION_ERROR,
                        offset,
                    ))

                self.actual_acquires.add(x)

        elif instruction.tag in [
            Opcodes.MOVE_FROM,
            Opcodes.MUT_BORROW_GLOBAL,
            Opcodes.IMM_BORROW_GLOBAL,
            ]:
            (idx, _) = instruction.value
            if idx not in self.annotated_acquires:
                self.errors.append(err_at_offset(
                    StatusCode.MISSING_ACQUIRES_RESOURCE_ANNOTATION_ERROR,
                    offset,
                ))

            self.actual_acquires.add(idx)
        else:
            pass

