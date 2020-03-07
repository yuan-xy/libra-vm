from __future__ import annotations
from bytecode_verifier.ref_id import RefID
from typing import List, Any, Optional, Mapping, Set
from dataclasses import dataclass
from copy import deepcopy
from enum import IntEnum
from libra.rustlib import assert_true, flatten

checked_assume = assert_true
checked_postcondition = assert_true
checked_precondition = assert_true
checked_verify = assert_true

# This module defines the (acyclic) borrow graph for the type and memory safety analysis.
# A node in the borrow graph represents an abstract reference.  Each edge in the borrow graph
# is labeled with a (possibly empty) sequence of label elements.  A label element is either a
# field index or a local index or a class index.  An edge coming out of frame_root
# (see abstract_state.rs) is labeled with a sequence beginning with a local or class index
# followed by zero or more field indices.  An edge coming out of a node different from frame_root
# is labeled by a sequence of zero or more field indices.

# An edge in the borrow graph from a node other than frame_root represents a prefix relationship
# between the references represented by the source and sink of the edge.  There are two kinds of
# edges---strong and weak.  A strong edge from node a to b labeled by sequence p indicates that
# b is equal to the p-extension of a.  Instead, if the edge was weak, it indicates that b is an
# extension of the p-extension of a.




# The type of an edge

class EdgeType(IntEnum):
    Strong = 1
    Weak = 2


# The label on an edge
Label= List

def starts_with(label1, label2):
    return len(label2) <= len(label1) and label1[0:len(label2)] == label2

# A labeled edge in borrow graph
@dataclass
class Edge:
    edge_type: EdgeType
    label: Label[Any]
    to: RefID

    def __hash__(self):
        return (self.edge_type, tuple(self.label), self.to).__hash__()


    def is_prefix(self, other: Edge) -> bool:
        return self == other or (
            self.edge_type == EdgeType.Weak \
            and starts_with(other.label, self.label) \
            and self.to == other.to)


# A borrow graph is represented as a map from a source id to the set of all edges
# coming out of it.
@dataclass
class BorrowGraph:
    v0: Mapping[RefID, Set[Edge]] #BTreeMap<RefID, BTreeSet<Edge<T>>>)

    # creates a new empty borrow graph
    @classmethod
    def new(cls) -> BorrowGraph:
        return cls({})


    # adds a fresh id
    def add(self, rid: RefID):
        checked_precondition(rid not in self.v0)
        self.v0[rid] = set()


    # adds a weak edge
    def add_weak_edge(self, frm: RefID, label: Label, to: RefID):
        checked_precondition(frm in self.v0)
        checked_precondition(to in self.v0)
        checked_precondition(self.v0[to].__len__() == 0)
        new_edge = Edge(EdgeType.Weak, label, to)
        self.v0[frm].add(new_edge)


    # adds a strong edge and factors other edges coming out of `from` with respect to the new edge
    def add_strong_edge(self, frm: RefID, label: Label, to: RefID):
        checked_precondition(frm in self.v0)
        checked_precondition(to in self.v0)
        checked_precondition(self.v0[to].__len__() == 0)
        checked_precondition(label.__len__() <= 1)

        new_edge = Edge(EdgeType.Strong, deepcopy(label), to)

        self.v0.pop(to)
        from_edge_set = self.v0.pop(frm)
        if not label:
            new_from_edge_set = set()
            new_from_edge_set.add(new_edge)

            self.v0[frm] = new_from_edge_set
            self.v0[to] = from_edge_set
        else:
            lamb = lambda x: x.label and x.label[0] == label[0]
            (new_to_edges, new_from_edge_set) = BorrowGraph.split(from_edge_set, lamb)
            new_from_edge_set.add(new_edge)
            for x in new_to_edges:
                x.label.pop(0)

            self.v0[frm] = new_from_edge_set
            self.v0[to] = set(new_to_edges)

    # removes `id` and appropriately concatenates each incoming edge with each outgoing edge of `id`
    def remove(self, rid: RefID):
        checked_assume(self.invariant())
        id_edge_set = self.v0.pop(rid)

        def lambda0():
            x = {}
            for (n, es) in self.v0.items():
                x[deepcopy(n)] = [x for x in es if x.to == rid]
            return x
        removed_edges = lambda0()

        for (n, es) in removed_edges.items():
            for removed_edge in es:
                n_edge_set_ref = self.v0[n]
                n_edge_set_ref.remove(removed_edge)
                for id_edge in id_edge_set:
                    # Avoid adding self edges in the case of cycles
                    if n == id_edge.to:
                        return

                    if removed_edge.edge_type == EdgeType.Strong:
                        new_label = []
                        new_label.extend(deepcopy(removed_edge.label))
                        new_label.extend(deepcopy(id_edge.label))
                        edge = Edge(
                            edge_type= id_edge.edge_type,
                            label= new_label,
                            to= id_edge.to,
                        )
                        n_edge_set_ref.add(edge)
                    else:
                        edge = Edge(
                            edge_type= EdgeType.Weak,
                            label= deepcopy(removed_edge.label),
                            to= id_edge.to,
                        )
                        n_edge_set_ref.add(edge)

        checked_verify(self.invariant())
        checked_postcondition(rid not in self.v0)


    # renames ids in `self` according to `id_map`
    def rename_ids(self, id_map: Mapping[RefID, RefID]) -> BorrowGraph:
        checked_assume(self.invariant())
        new_graph = {}
        for (n, es) in self.v0.items():
            key = id_map[n]
            v = {Edge(x.edge_type, deepcopy(x.label), id_map[x.to]) for x in es}
            new_graph[key] = v

        new_borrow_graph = BorrowGraph(new_graph)
        checked_verify(self.invariant())
        checked_verify(new_borrow_graph.invariant())
        return new_borrow_graph


    # checks if `self` covers `other`
    def abstracts(self, other: BorrowGraph) -> bool:
        for es in self.unmatched_edges(other).values():
            if es:
                return False
        return True


    # joins `other` into `self`
    def join(self, other: BorrowGraph):
        for (n, es) in self.unmatched_edges(other).items():
            self.v0[n].update(es)


    # gets all ids that are targets of outgoing edges from `id`
    def all_borrows(self, rid: RefID) -> Set[RefID]:
        checked_precondition(rid in self.v0)
        return {x.to for x in self.v0[rid]}


    # gets all ids that are targets of outgoing edges from `id` that are labeled with the empty label
    def nil_borrows(self, rid: RefID) -> Set[RefID]:
        checked_precondition(rid in self.v0)
        return {x.to for x in self.v0[rid] if not x.label}


    # gets all ids that are targets of outgoing edges from `id` that are consistent with `label_elem`
    def consistent_borrows(self, rid: RefID, label_elem: Any) -> Set[RefID]:
        checked_precondition(rid in self.v0)
        return {x.to for x in self.v0[rid] if not x.label or x.label[0] == label_elem}


    # split `edge_set` based on `pred` without cloning entries in `edge_set`
    @classmethod
    def split(cls, edge_set: Set[Edge], pred: Callable[[Edge], bool]) -> Tuple[List[Edge], Set[Edge]]:
        pred_True = []
        pred_False = set()
        for edge in edge_set:
            if pred(edge):
                pred_True.append(edge)
            else:
                pred_False.add(edge)

        return (pred_True, pred_False)


    def unmatched_edges(self, other: BorrowGraph) -> Mapping[RefID, Set[Edge]]:
        unmatched_edges = {}
        for (n, other_edges) in other.v0.items():
            unmatched_edges[deepcopy(n)] = set()
            for other_edge in other_edges:
                found_match = False
                for self_edge in self.v0[n]:
                    if self_edge.is_prefix(other_edge):
                        found_match = True
                        break

                if not found_match:
                    unmatched_edges[n].add(deepcopy(other_edge))

        return unmatched_edges


    def invariant(self) -> bool:
        for edges in self.v0.values():
            for edge in edges:
                if edge.to not in self.v0:
                    return False
                if flatten(edge.label) != edge.label:
                    return False
        for (n, edges) in self.v0.items():
            for edge in edges:
                if n == edge.to:
                    return False
        return True
