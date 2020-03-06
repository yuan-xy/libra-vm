from __future__ import annotations
from bytecode_verifier.absint import AbstractDomain, JoinResult
from bytecode_verifier.borrow_graph import BorrowGraph
from bytecode_verifier.ref_id import RefID
from typing import List, Any, Optional, Mapping, Set, Union
from dataclasses import dataclass
from copy import deepcopy
from enum import IntEnum
from libra_vm.file_format import (
        CompiledModule, FieldDefinitionIndex, Kind, LocalIndex, SignatureToken,
        StructDefinitionIndex,
    )
from libra_vm.views import FunctionDefinitionView, ViewInternals
from libra.rustlib import assert_true

checked_assume = assert_true
checked_postcondition = assert_true
checked_precondition = assert_true
checked_verify = assert_true


# This module defines the abstract state for the type and memory safety analysis.

@dataclass
class TypedAbstractValue:
    signature: SignatureToken
    value: AbstractValue


# AbstractValue represents a value either on the evaluation stack or
# in a local on a frame of the function stack.
@dataclass
class AbstractValue:
    tag: int
    value: Union[RefID, Kind]

    REFERENCE = 1
    VALUE = 2

    @classmethod
    def Reference(cls, rid:RefID) -> AbstractValue:
        return cls(AbstractValue.REFERENCE, rid)

    @classmethod
    def Value(cls, kind:Kind) -> AbstractValue:
        return cls(AbstractValue.VALUE, kind)


    # checks if self is a reference
    def is_reference(self) -> bool:
        if self.tag == AbstractValue.REFERENCE:
            return True
        else:
            return False


    # checks if self is a value
    def is_value(self) -> bool:
        return not self.is_reference()


    # checks if self is a non-resource value
    def is_unrestricted_value(self) -> bool:
        if self.tag == AbstractValue.VALUE:
            if self.value == Kind.Unrestricted:
                return True
            else:
                return False
        else:
            return False


    # checks if self is a resource or all value
    def is_possibly_resource(self) -> bool:
        if self.tag == AbstractValue.VALUE:
            if self.value == Kind.Unrestricted:
                return False
            else:
                return True
        else:
            return False


    # possibly extracts id from self
    def extract_id(self) -> Optional[RefID]:
        if self.tag == AbstractValue.REFERENCE:
            return self.value
        else:
            return None


# LabelElem is an element of a label on an edge in the borrow graph.
@dataclass
class LabelElem:
    tag: int
    value: Union[LocalIndex, StructDefinitionIndex, FieldDefinitionIndex]

    LOCAL = 1
    GLOBAL = 2
    FIELD = 3

    @classmethod
    def Local(cls, idx: LocalIndex) -> LabelElem:
        return cls(LabelElem.LOCAL, idx)

    @classmethod
    def Global(cls, idx: StructDefinitionIndex) -> LabelElem:
        return cls(LabelElem.GLOBAL, idx)

    @classmethod
    def Field(cls, idx: FieldDefinitionIndex) -> LabelElem:
        return cls(LabelElem.FIELD, idx)

    @classmethod
    def default(cls) -> LabelElem:
        return LabelElem.Local(0)


# AbstractState is the analysis state over which abstract interpretation is performed.
@dataclass
class AbstractState:
    locls: Mapping[LocalIndex, TypedAbstractValue]
    borrow_graph: BorrowGraph #<LabelElem>,
    num_locls: usize
    next_id: usize

    @classmethod
    def default(cls) -> AbstractState:
        return cls({}, BorrowGraph.new(), 0, 0)

    @classmethod
    def new(cls, function_definition_view: FunctionDefinitionView) -> AbstractState:
        function_signature_view = function_definition_view.signature()
        locls = {} #BTreeMap
        borrow_graph = BorrowGraph.new()
        for (arg_idx, arg_type_view) in enumerate(function_signature_view.arg_tokens()):
            if arg_type_view.is_reference():
                rid = RefID(arg_idx)
                borrow_graph.add(rid)
                locls[arg_idx] = \
                    TypedAbstractValue(
                        signature= deepcopy(arg_type_view.as_inner()),
                        value= AbstractValue.Reference(id),
                    )
            else:
                arg_kind = arg_type_view.kind(
                    function_definition_view.signature().as_inner().type_formals)
                locls[arg_idx] = \
                    TypedAbstractValue(
                        signature= deepcopy(arg_type_view.as_inner()),
                        value= AbstractValue.Value(arg_kind),
                    )

        num_locls = function_definition_view.locals_signature().__len__()
        # ids in [0, num_locls] are reserved for constructing canonical state
        next_id = num_locls + 1
        new_state = AbstractState(
            locls,
            borrow_graph,
            num_locls,
            next_id,
        )
        new_state.borrow_graph.add(new_state.frame_root())
        return new_state


    # checks if local@idx is available
    def is_available(self, idx: LocalIndex) -> bool:
        return idx in self.locls


    # returns local@idx
    def local(self, idx: LocalIndex) -> TypedAbstractValue:
        return self.locls[idx]


    # removes local@idx
    def remove_local(self, idx: LocalIndex) -> TypedAbstractValue:
        return self.locls.pop(idx)


    # inserts local@idx
    def insert_local(self, idx: LocalIndex, abs_type: TypedAbstractValue):
        self.locls[idx] = abs_type


    # checks if local@idx may be safely destroyed
    def is_local_safe_to_destroy(self, idx: LocalIndex) -> bool:
        av = self.locls[idx].value
        if av.tag == AbstractValue.REFERENCE:
            return True
        elif av.tag == AbstractValue.VALUE:
            if av.value == Kind.All or av.value == Kind.Resource:
                return False
            else:
                return not self.is_local_borrowed(idx)
        else:
            bail("unreachable!")


    # checks if the stack frame of the function being analyzed can be safely destroyed.
    # safe destruction requires that all references in locls have already been destroyed
    # and all values in locls are unrestricted and unborrowed.
    def is_frame_safe_to_destroy(self) -> bool:
        for x in self.locls.values():
            if not x.value.is_unrestricted_value():
                return False
        return not self.is_borrowed(self.frame_root())


    # destroys local@idx
    def destroy_local(self, idx: LocalIndex):
        checked_precondition(self.is_local_safe_to_destroy(idx))
        local = self.locls.pop(idx)
        av = local.value
        if av.tag == AbstractValue.REFERENCE:
            self.remove(av.value)
        elif av.tag == AbstractValue.VALUE:
            checked_verify(av.value == Kind.Unrestricted)
        else:
            bail("unreachable!")


    # returns the frame root id
    def frame_root(self) -> RefID:
        return RefID(self.num_locls)


    # adds and returns new id to borrow graph
    def add(self) -> RefID:
        rid = RefID(self.next_id)
        self.borrow_graph.add(rid)
        self.next_id += 1
        return rid


    # removes `id` from borrow graph
    def remove(self, id: RefID):
        self.borrow_graph.remove(id)


    # checks if `id` is borrowed
    def is_borrowed(self, id: RefID) -> bool:
        return self.borrow_graph.all_borrows(id).__len__() > 0


    def local_borrows(self, idx: LocalIndex) -> Set[RefID]:
        return self.borrow_graph\
            .consistent_borrows(self.frame_root(), LabelElem.Local(idx))


    # checks if local@idx is borrowed
    def is_local_borrowed(self, idx: LocalIndex) -> bool:
        return bool(self.local_borrows(idx))


    # checks if local@idx is mutably borrowed
    def is_local_mutably_borrowed(self, idx: LocalIndex) -> bool:
        return not self.all_immutable(self.local_borrows(idx))


    # checks if global@idx is borrowed
    def is_global_borrowed(self, idx: StructDefinitionIndex) -> bool:
        return bool(self.borrow_graph.consistent_borrows(
                self.frame_root(), LabelElem.Global(idx))
            )


    # checks if `id` is freezable
    def is_freezable(self, rid: RefID) -> bool:
        borrows = self.borrow_graph.all_borrows(rid)
        return bool(self.all_immutable(borrows))


    # update self to reflect a borrow of global@idx by a fresh id that is returned
    def borrow_global_value(self, mut_: bool, idx: StructDefinitionIndex) -> Optional[RefID]:
        if mut_:
            if self.is_global_borrowed(idx):
                return None

        else:
            borrowed_ids = self\
                .borrow_graph\
                .consistent_borrows(self.frame_root(), LabelElem.Global(idx))
            if not self.all_immutable(borrowed_ids):
                return None

        new_id = self.add()
        self.borrow_graph\
            .add_weak_edge(self.frame_root(), [LabelElem.Global(idx)], new_id)
        return new_id


    # update self to reflect a borrow of field@idx from operand.value by a fresh id that is returned
    def borrow_field(
        self,
        operand: TypedAbstractValue,
        mut_: bool,
        idx: FieldDefinitionIndex,
    ) -> Optional[RefID]:
        rid = operand.value.extract_id()
        if mut_:
            if self.borrow_graph.nil_borrows(rid):
                return None

        elif operand.signature.is_mutable_reference():
            borrowed_ids = self\
                .borrow_graph\
                .consistent_borrows(rid, LabelElem.Field(idx))
            if not self.all_immutable(borrowed_ids):
                return None

        new_id = self.add()
        self.borrow_graph.add_strong_edge(rid, [LabelElem.Field(idx)], new_id)
        return new_id


    # update self to reflect a borrow of local@idx (which must be a value) by a fresh id that is returned
    def borrow_local_value(self, mut_: bool, idx: LocalIndex) -> Optional[RefID]:
        checked_precondition(self.locls[idx].value.is_value())
        if not mut_:
            # nothing to check in case borrow is mutable since the frame cannot have a NIL outgoing edge
            borrowed_ids = self\
                .borrow_graph\
                .consistent_borrows(self.frame_root(), LabelElem.Local(idx))
            if not self.all_immutable(borrowed_ids):
                return None

        new_id = self.add()
        self.borrow_graph\
            .add_strong_edge(self.frame_root(), [LabelElem.Local(idx)], new_id)
        return new_id


    # update self to reflect a borrow of local@idx (which must be a reference) by a fresh id that is returned
    def borrow_local_reference(self, idx: LocalIndex) -> RefID:
        checked_precondition(self.locls[idx].value.is_reference())
        new_id = self.add()
        self.borrow_graph.add_strong_edge(
            self.locls[idx].value.extract_id(),
            [],
            new_id,
        )
        return new_id


    # update self to reflect a borrow from each id in to_borrow_from by a fresh id that is returned
    def borrow_from(self, to_borrow_from: Set[RefID]) -> RefID:
        new_id = self.add()
        for rid in to_borrow_from:
            self.borrow_graph.add_weak_edge(rid, [], new_id)

        return new_id


    # returns the canonical representation of self
    def construct_canonical_state(self) -> AbstractState:
        id_map = {} #BTreeMap.new()
        id_map[self.frame_root()] = self.frame_root()
        def lambda0(idx, abv):
            if abv.value.tag == AbstractValue.REFERENCE:
                rid = abv.value.value
                new_id = RefID(idx)
                id_map[rid] = new_id
                new_abs = TypedAbstractValue(
                    signature= deepcopy(abv.signature),
                    value= AbstractValue.Reference(new_id),
                )
            else:
                new_abs = deepcopy(abv)
            return (idx, new_abs)

        locls = {}
        for (idx, abv) in self.locls.items():
            (idx, abv) = lambda0(idx, abv)
            locls[idx] = abv

        checked_verify(self.locls.__len__() == locls.__len__())
        canonical_state = AbstractState(
            locls = locls,
            borrow_graph= self.borrow_graph.rename_ids(id_map),
            num_locls= self.num_locls,
            next_id= self.num_locls + 1,
        )
        checked_postcondition(canonical_state.is_canonical())
        return canonical_state


    def all_immutable(self, borrows: Set[RefID]) -> bool:
        for abs_type in self.locls.values():
            if abs_type.signature.is_mutable_reference()\
                and borrows.contains(abs_type.value.extract_id()):
                return False
        return True


    def is_canonical(self) -> bool:
        if self.num_locls + 1 != self.next_id:
            return False
        for (x, y) in self.locls:
            if y.value.is_reference() and RefID(x) != y.value.extract_id():
                return False
        return True


    def iter_locls(self) -> Iterable[LocalIndex]:
        return range(self.num_locls)


    # returns `Some` of the self joined with other,
    # returns `None` if there is a join error
    def join_(self, other: AbstractState) -> Optional[AbstractState]:
        checked_precondition(self.is_canonical() and other.is_canonical())
        checked_precondition(self.next_id == other.next_id)
        checked_precondition(self.num_locls == other.num_locls)
        locls = {} #BTreeMap.new()
        self_graph = deepcopy(self.borrow_graph)
        other_graph = deepcopy(other.borrow_graph)
        for idx in self.iter_locls():
            self_value = self.locls[idx]
            other_value = other.locls[idx]
            if self_value is None:
                if other_value is None:
                    # Unavailable on both sides, nothing to add
                    pass
                else:
                    # Join error, a resource is available along one path but not the other
                    if other_value.value.is_possibly_resource():
                        return None
                    else:
                        # A reference exists on one side, but not the other. Release
                        if other_value.value.tag == AbstractValue.REFERENCE:
                            other_graph.remove(other_value.value.value)
            else:
                if other_value is None:
                    # Join error, a resource is available along one path but not the other
                    if self_value.value.is_possibly_resource():
                        return None
                    else:
                        # A reference exists on one side, but not the other. Release
                        if self_value.value.tag == AbstractValue.REFERENCE:
                            self_graph.remove(self_value.value.value)
                else:
                    # The local has a value on each side, add it to the state
                    checked_verify(self_value == other_value)
                    checked_verify(idx not in locls)
                    locls[idx] = deepcopy(v1)

        self_graph.join(other_graph)
        borrow_graph = self_graph
        next_id = self.next_id
        num_locls = self.num_locls

        return AbstractState(
            locls,
            borrow_graph,
            next_id,
            num_locls,
        )


# impl AbstractDomain for AbstractState {
    # attempts to join state to self and returns the result
    def join(self, state: AbstractState) -> JoinResult:
        joined = AbstractState.join_(self, state)
        if joined is None:
            return JoinResult.Error,

        checked_verify(self.num_locls == joined.num_locls)
        locls_unchanged = True
        for idx in self.iter_locls():
            if self.locls.get(idx) != joined.locls.get(idx):
                locls_unchanged = False
                break
        borrow_graph_unchanged = self.borrow_graph.abstracts(joined.borrow_graph)
        if locls_unchanged and borrow_graph_unchanged:
            return JoinResult.Unchanged
        else:
            # *self = joined
            self.replace_with(joined)
            return JoinResult.Changed

    def replace_with(self, other):
        self.locls = other.locls
        self.borrow_graph = other.borrow_graph
        self.num_locls = other.num_locls
        self.next_id = other.next_id