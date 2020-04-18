from mol.bytecode_verifier.control_flow_graph import VMControlFlowGraph
from mol.bytecode_verifier.acquires_list_verifier import AcquiresVerifier
from mol.bytecode_verifier.stack_usage_verifier import StackUsageVerifier
from mol.bytecode_verifier.type_memory_safety import TypeAndMemorySafetyAnalysis
from libra.vm_error import StatusCode, VMStatus
from mol.vm.errors import append_err_info
from mol.vm.file_format import CompiledModule, FunctionDefinition
from mol.vm import IndexKind, ModuleAccess
from typing import List, Optional
from dataclasses import dataclass
from libra.rustlib import flatten

# This module implements the checker for verifying correctness of function bodies.
# The overall verification is split between stack_usage_verifier.rs and
# abstract_interpreter.rs. CodeUnitVerifier simply orchestrates calls into these two files.

@dataclass
class CodeUnitVerifier:
    module: CompiledModule

    @classmethod
    def verify(cls, module: CompiledModule) -> List[VMStatus]:
        verifier = cls(module)
        ret = []
        for (idx, function_definition) in enumerate(verifier.module.function_defs()):
            errors = flatten(verifier.verify_function(function_definition))
            for err in errors:
                append_err_info(err, IndexKind.FunctionDefinition, idx)
                ret.append(err)
        return ret



    def verify_function(self, function_definition: FunctionDefinition) -> List[VMStatus]:
        if function_definition.is_native():
            return []

        code = function_definition.code.code

        # Check to make sure that the bytecode vector ends with a branching instruction.

        if code:
            bytecode = code[-1]
            if not bytecode.is_unconditional_branch():
                return [VMStatus(StatusCode.INVALID_FALL_THROUGH)]
        else:
            return [VMStatus(StatusCode.INVALID_FALL_THROUGH)]

        return self.verify_function_inner(function_definition, VMControlFlowGraph.new(code))


    def verify_function_inner(
        self,
        function_definition: FunctionDefinition,
        cfg: VMControlFlowGraph,
    ) -> List[VMStatus]:
        errors = StackUsageVerifier.verify(self.module, function_definition, cfg)
        if errors:
            return errors

        errors = AcquiresVerifier.verify(self.module, function_definition)
        if errors:
            return errors

        return TypeAndMemorySafetyAnalysis.verify(self.module, function_definition, cfg)
