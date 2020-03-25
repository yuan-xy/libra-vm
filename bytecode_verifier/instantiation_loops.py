from __future__ import annotations
from libra_vm import SerializedType, Opcodes
from libra.vm_error import StatusCode, VMStatus
from libra_vm.file_format import (
        Bytecode, CompiledModule, FunctionDefinition, FunctionDefinitionIndex, FunctionHandleIndex,
        LocalsSignatureIndex, SignatureToken, TypeParameterIndex, ModuleAccess
    )
from typing import List, Optional, Mapping, Tuple
from dataclasses import dataclass
from pygraph.classes.digraph import digraph
from pygraph.algorithms.accessibility import mutual_accessibility
from libra.rustlib import format_str

# This implements an algorithm that detects loops during the instantiation of generics.
#
# It builds a graph from the given `CompiledModule` and converts the original problem into
# finding strongly connected components in the graph with certain properties. Read the
# documentation of the types/functions below for details of how it works.
#
# Note: We're doing generics only up to specialization, and are doing a conservative check of
# generic call sites to eliminate those which could lead to an infinite number of specialized
# instances. We do reject recursive functions that create a new type upon each call but do
# terminate eventually.



# Data attached to each node.
# Each node corresponds to a type formal of a generic function in the module.
@dataclass
class Node:
    v0: FunctionDefinitionIndex
    v1: TypeParameterIndex

    def __hash__(self):
        return (self.v0.v0, self.v1).__hash__()

    def __lt__(self, other):
        if self.v0.v0 == other.v0.v0:
            return self.v1 < other.v1
        else:
            return self.v0.v0 < other.v0.v0

# Data attached to each edge. Indicating the type of the edge.
@dataclass
class Edge:
    tag: int
    value: SignatureToken = None

    IDENTITY = 1
    TYCONAPP = 2

    # This type of edge from type formal T1 to T2 means the type bound to T1 is used to
    # instantiate T2 unmodified, thus the name `Identity`.
    #
    # Example:
    # ```
    # #    foo<T>() { bar<T>(); return; }
    # //
    # #    edge: foo_T --Id--> bar_T
    # ```
    @classmethod
    def Identity(cls):
        return cls(cls.IDENTITY)

    # This type of edge from type formal T1 to T2 means T2 is instantiated with a type resulted
    # by applying one or more type constructors to T1 (potentially with other types).
    #
    # This is interesting to us as it creates a new (and bigger) type.
    #
    # Example:
    # ```
    # #    class Baz<T> {}
    # #    foo<T>() { bar<Baz<T>>(); return; }
    # //
    # #    edge: foo_T --TyConApp(Baz<T>)--> bar_T
    # ```
    @classmethod
    def TyConApp(cls, token: SignatureToken):
        return cls(cls.TYCONAPP, token)


EdgeInGraph = Tuple[Node, Node]


@dataclass
class InstantiationLoopChecker:
    module: CompiledModule
    graph: digraph #Graph<Node, Edge>
    # node_map: Mapping[Node, NodeIndex]
    func_handle_def_map: Mapping[FunctionHandleIndex, FunctionDefinitionIndex]

    @classmethod
    def new(cls, module: CompiledModule) -> InstantiationLoopChecker:
        func_handle_def_map = {}
        for (def_idx, fdef) in enumerate(module.function_defs()):
            func_handle_def_map[fdef.function] = FunctionDefinitionIndex.new(def_idx)

        return cls(module, digraph(), func_handle_def_map)


    # Retrives the node corresponding to the specified type formal.
    # If none exists in the graph yet, create one.
    # def get_or_add_node(self, node: Node) -> NodeIndex {
    #     match self.node_map.entry(node) {
    #         hash_map.Entry.Occupied(entry) => *entry.get(),
    #         hash_map.Entry.Vacant(entry) => {
    #             idx = self.graph.add_node(node)
    #             entry.insert(idx)
    #             idx
    #         }
    #     }
    # }

    # Helper function that extracts type parameters from a given type.
    # Duplicated entries are removed.
    @classmethod
    def extract_type_parameters(cls, ty: SignatureToken) -> Set[TypeParameterIndex]:
        type_params = set()

        def rec(type_params: Set[TypeParameterIndex], ty: SignatureToken):
            if ty.tag in [
                SerializedType.BOOL,
                SerializedType.ADDRESS,
                SerializedType.U8,
                SerializedType.U64,
                SerializedType.U128,
                SerializedType.BYTEARRAY,
            ]:
                return
            elif ty.tag == SerializedType.TYPE_PARAMETER:
                type_params.add(ty.typeParameter)
            elif ty.tag == SerializedType.VECTOR:
                rec(type_params, ty.vector_type)
            elif ty.tag == SerializedType.REFERENCE or ty.tag == SerializedType.MUTABLE_REFERENCE:
                rec(type_params, ty.reference)
            elif ty.tag == SerializedType.STRUCT:
                (_, tys) = ty.struct
                for ty in tys:
                    rec(type_params, ty)

        rec(type_params, ty)
        return type_params


    # Helper function that creates an edge from one given node to the other.
    # If a node does not exist, create one.
    def add_edge(self, node_from: Node, node_to: Node, edge: Edge):
        if not self.graph.has_node(node_from):
            self.graph.add_node(node_from)
        if not self.graph.has_node(node_to):
            self.graph.add_node(node_to)
        self.graph.add_edge((node_from, node_to), attrs = [('data',edge)])


    # Helper of 'def build_graph' that inspects a function call. If type parameters of the caller
    # appear in the type actuals to the callee, nodes and edges are added to the graph.
    def build_graph_call(
        self,
        caller_idx: FunctionDefinitionIndex,
        callee_idx: FunctionDefinitionIndex,
        type_actuals_idx: LocalsSignatureIndex,
    ):
        type_actuals = self.module.locals_signature_at(type_actuals_idx).v0

        for (formal_idx, ty) in enumerate(type_actuals):
            if ty.tag == SerializedType.TYPE_PARAMETER:
                actual_idx = ty.typeParameter
                self.add_edge(
                    Node(caller_idx, actual_idx),
                    Node(callee_idx, formal_idx),
                    Edge.Identity(),
                )
            else:
                for type_param in self.__class__.extract_type_parameters(ty):
                    self.add_edge(
                        Node(caller_idx, type_param),
                        Node(callee_idx, formal_idx),
                        Edge.TyConApp(ty),
                    )



    # Helper of `def build_graph` that inspects a function definition for calls between two generic
    # functions defined in the current module.
    def build_graph_function_def(
        self,
        caller_idx: FunctionDefinitionIndex,
        caller_def: FunctionDefinition,
    ):
        for instr in caller_def.code.code:
            if instr.tag == Opcodes.CALL:
                (callee_handle_idx, type_actuals_idx) = instr.value
                # Get the id of the definition of the function being called.
                # Skip if the function is not defined in the current module, as we do not
                # have mutual recursions across module boundaries.
                if callee_handle_idx in self.func_handle_def_map:
                    callee_idx = self.func_handle_def_map[callee_handle_idx]
                    self.build_graph_call(caller_idx, callee_idx, type_actuals_idx)


    # Builds a graph G such that
    #   - Each type formal of a generic function is a node in G.
    #   - There is an edge from type formal f_T to g_T if f_T is used to instantiate g_T in a
    #     call.
    #     - Each edge is labeled either `Identity` or `TyConApp`. See `Edge` for details.
    def build_graph(self):
        for (def_idx, func_def) in enumerate(self.module.function_defs()):
            if func_def.is_native():
                continue

            self.build_graph_function_def(FunctionDefinitionIndex.new(def_idx), func_def)


    # Computes the strongly connected components of the graph built and keep the ones that
    # contain at least one `TyConApp` edge. Such components indicate there exists a loop such
    # that an input type can get "bigger" infinitely many times along the loop, also creating
    # infinitely many types. This is precisely the kind of constructs we want to forbid.
    def find_non_trivial_components(self) -> List[Tuple[List[Node], List[EdgeInGraph]]]:
        ma = mutual_accessibility(self.graph)
        sccs = {tuple(x) for x in ma.values()}
        ret = []
        for nodes in sccs:
            edges = []
            for node in nodes:
                ns = self.graph.neighbors(node)
                for n in ns:
                    if n in nodes:
                        edges.append((node, n))

            for eg in edges:
                edge: Edge = self.get_edge_data(eg)
                if edge.tag == Edge.TYCONAPP:
                    ret.append((nodes, edges))
        return ret



    def format_node(self, node: Node) -> str:
        return format_str("f{}#{}", node.v0, node.v1)


    def format_edge(self, eg: EdgeInGraph) -> str:
        node_1 = self.format_node(eg[0])
        node_2 = self.format_node(eg[1])

        edge: Edge = self.get_edge_data(eg)
        if edge.tag == Edge.TYCONAPP:
            ty = edge.value
            return format_str("{} --{}--> {}", node_1, ty, node_2)
        else:
            return format_str("{} ----> {}", node_1, node_2)


    def get_edge_data(self, eg: EdgeInGraph) -> Edge:
        arr = self.graph.edge_attributes(eg)
        for name, edge in arr:
            if name =='data':
                return edge
        return None


    def verify(self) -> List[VMStatus]:
        self.build_graph()
        components = self.find_non_trivial_components()

        def lambda0(nodes, edges):
            msg_edges = [self.format_edge(eg) for eg in edges \
                if self.get_edge_data(eg).tag == Edge.TYCONAPP]
            msg_edges = ", ".join(msg_edges)
            msg_nodes = [self.format_node(x) for x in nodes]
            msg_nodes = ", ".join(msg_nodes)
            msg = format_str(
                "edges with constructors: [{}], nodes: [{}]",
                msg_edges, msg_nodes
            )
            return VMStatus(StatusCode.LOOP_IN_INSTANTIATION_GRAPH).with_message(msg)

        return [lambda0(nodes, edges) for (nodes, edges) in components]
