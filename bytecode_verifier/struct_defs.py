from __future__ import annotations
from libra.vm_error import StatusCode, VMStatus
from libra_vm.errors import verification_error
from libra_vm import ModuleAccess, IndexKind
from libra_vm.internals import ModuleIndex
from libra_vm.views import StructDefinitionView
from libra_vm.file_format import CompiledModule, StructDefinitionIndex, StructHandleIndex, TableIndex
from dataclasses import dataclass
from typing import List, Optional, Mapping, Callable, Any, Tuple

from pygraph.classes.digraph import digraph
from pygraph.algorithms.sorting import topological_sorting
from pygraph.algorithms.cycles import find_cycle

# This module provides a checker for verifing that class definitions in a module are not
# recursive. Since the module dependency graph is acylic by construction, applying this checker to
# each module in isolation guarantees that there is no structural recursion globally.

@dataclass
class RecursiveStructDefChecker:
    module: CompiledModule


    def verify(self) -> List[VMStatus]:
        graph_builder = StructDefGraphBuilder.new(self.module)

        graph = graph_builder.build()

        # toposort is iterative while petgraph.algo.is_cyclic_directed is recursive. Prefer
        # the iterative solution here as this code may be dealing with untrusted data.
        if find_cycle(graph):
            sd_idx = graph[cycle.node_id()]
            return [verification_error(
                IndexKind.StructDefinition,
                sd_idx.into_index(),
                StatusCode.RECURSIVE_STRUCT_DEFINITION,
            )]
        else:
            return []



# Given a module, build a graph of class definitions. This is useful when figuring out whether
# the class definitions in module form a cycle.
@dataclass
class StructDefGraphBuilder:
    module: CompiledModule
    # Used to follow field definitions' signatures' class handles to their class definitions.
    handle_to_def: Mapping[StructHandleIndex, StructDefinitionIndex]

    @classmethod
    def new(cls, module: CompiledModule) -> StructDefGraphBuilder:
        handle_to_def = {} #BTreeMap
        # the mapping from class definitions to class handles is already checked to be 1-1 by
        # DuplicationChecker
        for (idx, struct_def) in enumerate(module.struct_defs()):
            sh_idx = struct_def.struct_handle
            handle_to_def[sh_idx] = StructDefinitionIndex.new(idx)

        return cls(module, handle_to_def)


    def build(self) -> digraph:
        graph = digraph()

        struct_def_count = self.module.struct_defs().__len__()

        nodes = [StructDefinitionIndex.new(idx) for idx in range(struct_def_count)]
        graph.add_nodes(nodes)

        for idx in range(struct_def_count):
            sd_idx = StructDefinitionIndex.new(idx)
            for followed_idx in set(self.member_struct_defs(sd_idx)):
                graph.add_edge((sd_idx, followed_idx))

        return graph


    def member_struct_defs(
        self,
        idx: StructDefinitionIndex,
    ) -> List[StructDefinitionIndex]:
        struct_def = self.module.struct_def_at(idx)
        struct_def = StructDefinitionView.new(self.module, struct_def)
        fields = struct_def.fields()
        handle_to_def = self.handle_to_def

        ret = []
        for field in fields:
            type_signature = field.type_signature()
            sh_idx = type_signature.token().struct_index()
            if sh_idx in handle_to_def:
                ret.append(handle_to_def[sh_idx])
            else:
                # This field refers to a struct in another module.
                pass

        return ret
