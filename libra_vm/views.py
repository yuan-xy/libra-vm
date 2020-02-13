from __future__ import annotations
from libra_vm.access import ModuleAccess
from libra_vm.file_format import (
    CodeUnit, CompiledModule, FieldDefinition, FunctionDefinition, FunctionHandle,
    FunctionSignature, Kind, LocalIndex, LocalsSignature, ModuleHandle, SignatureToken,
    StructDefinition, StructDefinitionIndex, StructFieldInformation, StructHandle,
    StructHandleIndex, TypeSignature
    )
from libra_vm.lib import SignatureTokenKind
from libra.identifier import IdentStr
from libra.language_storage import ModuleId, StructTag
from typing import List, Set, Optional, Tuple, Mapping, Any
from dataclasses import dataclass
import abc

# An alternate representation of the file format built on top of the existing format.
#
# Some general notes:
#
# * These views are not meant to be set in stone. Feel free to change the views exposed as the
#   format and our understanding evolves.
# * The typical use for these views would be to materialize all the lazily evaluated data
#   immediately -- the views are a convenience to make that simpler. They've been written as lazy
#   iterators to aid understanding of the file format and to make it easy to generate views.


# This is used to expose some view internals to checks and other areas. This might be exposed
# to external code in the future.
class ViewInternals(abc.ABC):
    # @abc.abstractmethod
    # def module(self) -> ModuleAccess:

    @abc.abstractmethod
    def as_inner(self) -> Any:
        pass



# Represents a lazily evaluated abstraction over a module.
#
# `T` here is any sort of ``. See the documentation in access.rs for more.
@dataclass
class ModuleView(ViewInternals):
    module: ModuleAccess
    name_to_function_definition_view: Mapping[IdentStr, FunctionDefinitionView]#BTreeMap
    name_to_struct_definition_view: Mapping[IdentStr, StructDefinitionView]#BTreeMap

    def as_inner(self) -> ModuleAccess:
        return self.module

    @classmethod
    def new(cls, module: ModuleAccess) -> ModuleView:
        name_to_function_definition_view = {}
        for function_def in module.function_defs():
            view = FunctionDefinitionView.new(module, function_def)
            name_to_function_definition_view[view.name()] = view

        name_to_struct_definition_view = {}
        for struct_def in module.struct_defs():
            view = StructDefinitionView.new(module, struct_def)
            name_to_struct_definition_view[view.name()] = view

        return cls(
            module,
            name_to_function_definition_view,
            name_to_struct_definition_view,
        )


    def module_handles(
        self,
    ) -> List[ModuleHandleView]:
        module = self.module
        return [ModuleHandleView.new(module, x) for x in module.module_handles()]


    def struct_handles(
        self,
    ) -> List[StructHandleView]:
        module = self.module
        return [StructHandleView.new(module, x) for x in module.struct_handles()]


    def function_handles(
        self,
    ) -> List[FunctionHandleView]:
        module = self.module
        return [FunctionHandleView.new(module, x) for x in module.function_handles()]


    def structs(self) -> List[StructDefinitionView]:
        module = self.module
        return [StructDefinitionView.new(module, x) for x in module.struct_defs()]


    def fields(self) -> List[FieldDefinitionView]:
        module = self.module
        return [FieldDefinitionView.new(module, x) for x in module.field_defs()]


    def functions(
        self,
    ) -> List[FunctionDefinitionView]:
        module = self.module
        return [FunctionDefinitionView.new(module, x) for x in module.function_defs()]


    def type_signatures(
        self,
    ) -> List[TypeSignatureView]:
        module = self.module
        return [TypeSignatureView.new(module, x) for x in module.type_signatures()]


    def function_signatures(
        self,
    ) -> List[FunctionSignatureView]:
        module = self.module
        return [FunctionSignatureView.new(module, x) for x in module.function_signatures()]


    def locals_signatures(
        self,
    ) -> List[LocalsSignatureView]:
        module = self.module
        return [LocalsSignatureView.new(module, x) for x in module.locals_signatures()]


    def function_definition(
        self,
        name: IdentStr,
    ) -> Optional[FunctionDefinitionView]:
        return self.name_to_function_definition_view[name]


    def struct_definition(self, name: IdentStr) -> Optional[StructDefinitionView]:
        return self.name_to_struct_definition_view[name]


    def function_acquired_resources(
        self,
        function_handle: FunctionHandle,
    ) -> Set[StructDefinitionIndex]:
        if function_handle.module.v0 != CompiledModule.IMPLEMENTED_MODULE_INDEX:
            return set()

        # TODO these unwraps should be VMInvariantViolations
        function_name = self.as_inner().identifier_at(function_handle.name)
        function_def = self.function_definition(function_name)
        return deepcopy(function_def.as_inner().acquires_global_resources)


    def id(self) -> ModuleId:
        return self.module.self_id()


    # Return the `StructHandleIndex` that corresponds to the normalized type `t` in this module's
    # table of `StructHandle`'s. Returns `None` if there is no corresponding handle
    def resolve_struct(self, t: StructTag) -> Optional[StructHandleIndex]:
        for (idx, handle) in enumerate(self.module.struct_handles()):
            if StructHandleView.new(self.module, handle).normalize_struct() == t:
                return StructHandleIndex(idx)
        return None


@dataclass
class ModuleHandleView(ViewInternals):
    module: ModuleAccess
    module_handle: ModuleHandle

    def as_inner(self):
        return self.module_handle

    @classmethod
    def new(cls, module, module_handle: ModuleHandle) -> ModuleHandleView:
        return cls(module, module_handle)

    def module_id(self) -> ModuleId:
        return self.module.module_id_for_handle(self.module_handle)


@dataclass
class StructHandleView(ViewInternals):
    module: ModuleAccess
    struct_handle: StructHandle

    def as_inner(self):
        return self.struct_handle

    def handle(self) -> StructHandle:
        return self.struct_handle

    def is_nominal_resource(self) -> bool:
        return self.struct_handle.is_nominal_resource


    def type_formals(self) -> List[Kind]:
        return self.struct_handle.type_formals


    def module_handle(self) -> ModuleHandle:
        return self.module.module_handle_at(self.struct_handle.module)


    def name(self) -> IdentStr:
        return self.module.identifier_at(self.struct_handle.name)


    def module_id(self) -> ModuleId:
        return self.module.module_id_for_handle(self.module_handle())


    # Return the StructHandleIndex of this handle in the module's struct handle table
    def handle_idx(self) -> StructHandleIndex:
        for (idx, handle) in enumerate(self.module.struct_handles()):
            if handle == self.handle():
                return StructHandleIndex(idx)

        bail("Cannot resolve StructHandle {} in module {}. This should never happen in a well-formed `StructHandleView`. Perhaps this handle came from a different module?", self.handle(), self.module().name())


    # Return a normalized representation of this struct type that can be compared across modules
    def normalize_struct(self) -> StructTag:
        module_id = self.module_id()
        return StructTag(
            module = module_id.name(),
            address = module_id.address(),
            name = self.name(),
            # TODO: take type params as input
            type_params = [],
        )


@dataclass
class FunctionHandleView(ViewInternals):
    module: ModuleAccess
    function_handle: FunctionHandle

    def as_inner(self):
        return self.function_handle

    def module_handle(self) -> ModuleHandle:
        return self.module.module_handle_at(self.function_handle.module)

    def name(self) -> IdentStr :
        return self.module.identifier_at(self.function_handle.name)

    def signature(self) -> FunctionSignatureView:
        function_signature = self.module \
            .function_signature_at(self.function_handle.signature)
        return FunctionSignatureView.new(self.module, function_signature)

    def module_id(self) -> ModuleId :
        return self.module.module_id_for_handle(self.module_handle())


@dataclass
class StructDefinitionView(ViewInternals):
    module: ModuleAccess
    struct_def: StructDefinition
    struct_handle_view: StructHandleView

    def as_inner(self):
        return self.struct_def

    @classmethod
    def new(cls, module: ModuleAccess, struct_def: StructDefinition) -> StructDefinitionView:
        struct_handle = module.struct_handle_at(struct_def.struct_handle)
        struct_handle_view = StructHandleView.new(module, struct_handle)
        return cls(
            module,
            struct_def,
            struct_handle_view,
        )

    def is_nominal_resource(self) -> bool :
        return self.struct_handle_view.is_nominal_resource()

    def is_native(self) -> bool :
        if self.struct_def.field_information.tag == SerializedNativeStructFlag.NATIVE:
            return True
        else:
            return False

    def type_formals(self) -> List[Kind] :
        return self.struct_handle_view.type_formals()

    def fields(
        self,
    ) -> Optional[List[FieldDefinitionView]]:
        module = self.module
        if self.struct_def.field_information.tag == SerializedNativeStructFlag.NATIVE:
            return None
        else:
            field_count = self.struct_def.field_information.field_count
            fields = self.struct_def.field_information.fields
            arr = module.field_def_range(field_count, fields)
            return [FieldDefinitionView.new(module, field_def) for field_def in arr]


    def name(self) -> IdentStr :
        return self.struct_handle_view.name()

    # Return a normalized representation of this struct type that can be compared across modules
    def normalize_struct(self) -> StructTag :
        return self.struct_handle_view.normalize_struct()


@dataclass
class FieldDefinitionView(ViewInternals):
    module: ModuleAccess
    field_def: FieldDefinition

    def as_inner(self):
        return self.field_defs


    def name(self) -> IdentStr :
        return self.module.identifier_at(self.field_def.name)

    def type_signature(self) -> TypeSignatureView:
        type_signature = self.module.type_signature_at(self.field_def.signature)
        return TypeSignatureView.new(self.module, type_signature)

    def signature_token(self) -> SignatureToken :
        return self.module.type_signature_at(self.field_def.signature).v0

    def signature_token_view(self) -> SignatureTokenView:
        return SignatureTokenView.new(self.module, self.signature_token())

    # Field definitions are always private.

    # The struct this field is defined in.
    def member_of(self) -> StructHandleView:
        struct_handle = self.module.struct_handle_at(self.field_def.struct_)
        return StructHandleView.new(self.module, struct_handle)

    # Return a normalized representation of the type of this field's declaring struct that can be
    # compared across modules
    def normalize_declaring_struct(self) -> StructTag :
        return self.member_of().normalize_struct()


@dataclass
class FunctionDefinitionView(ViewInternals):
    module: ModuleAccess
    function_def: FunctionDefinition
    function_handle_view: FunctionHandleView

    def as_inner(self):
        return self.function_def

    @classmethod
    def new(cls, module: ModuleAccess, function_def: FunctionDefinition) -> FunctionDefinitionView:
        function_handle = module.function_handle_at(function_def.function)
        function_handle_view = FunctionHandleView.new(module, function_handle)
        return cls(
            module,
            function_def,
            function_handle_view,
        )

    def is_public(self) -> bool :
        return self.function_def.is_public()

    def is_native(self) -> bool :
        return self.function_def.is_native()

    def locals_signature(self) -> LocalsSignatureView:
        locals_signature = self.module \
            .locals_signature_at(self.function_def.code.locals)
        return LocalsSignatureView.new(self.module, locals_signature)

    def name(self) -> IdentStr :
        return self.function_handle_view.name()

    def signature(self) -> FunctionSignatureView:
        return self.function_handle_view.signature()

    def code(self) -> CodeUnit :
        return self.function_def.code

@dataclass
class TypeSignatureView(ViewInternals):
    module: ModuleAccess
    type_signature: TypeSignature

    def as_inner(self):
        return self.type_signatures


    def token(self) -> SignatureTokenView:
        return SignatureTokenView.new(self.module, self.type_signature.v0)


    def kind(self, type_formals: List[Kind]) -> Kind :
        return self.token().kind(type_formals)


    def contains_nominal_resource(self, type_formals: List[Kind]) -> bool :
        return self.token().contains_nominal_resource(type_formals)


@dataclass
class FunctionSignatureView(ViewInternals):
    module: ModuleAccess
    function_signature: FunctionSignature

    def as_inner(self):
        return self.function_signatures

    def return_tokens(self) -> List[SignatureTokenView]:
        module = self.module
        return [SignatureTokenView.new(module, t) for t in self.function_signature.return_types]

    def arg_tokens(self) -> List[SignatureTokenView]:
        module = self.module
        return [SignatureTokenView.new(module, t) for t in self.function_signature.arg_types]


    def type_formals(self) -> List[Kind] :
        return self.function_signature.type_formals

    def return_count(self) -> usize :
        return self.function_signature.return_types.__len__()

    def arg_count(self) -> usize :
        return self.function_signature.arg_types.__len__()


class LocalsSignatureView(ViewInternals):
    module: ModuleAccess
    locals_signature: LocalsSignature

    def as_inner(self):
        return self.locals_signature

    def len(self) -> usize :
        return self.locals_signature.v0.__len__()


    def is_empty(self) -> bool :
        return self.__len__() == 0


    def tokens(self) -> List[SignatureTokenView]:
        module = self.module
        return [SignatureTokenView.new(module, t) for t in self.locals_signature.v0]

    def token_at(self, index: LocalIndex) -> SignatureTokenView:
        return SignatureTokenView.new(self.module, self.locals_signature.v0[index])

@dataclass
class SignatureTokenView(ViewInternals):
    module: ModuleAccess
    token: SignatureToken

    def as_inner(self):
        return self.token

    def struct_handle(self) -> Optional[StructHandleView]:
        return [StructHandleView.new(self.module, self.module.struct_handle_at(sh_idx)) \
            for sh_idx in self.struct_index()]

    def signature_token(self) -> SignatureToken :
        return self.token


    def signature_token_kind(self) -> SignatureTokenKind :
        return self.token.signature_token_kind()

    # TODO: rework views to make the interfaces here cleaner.
    def kind(self, type_formals: List[Kind]) -> Kind :
        return SignatureToken.kind((self.module.struct_handles(), type_formals), self.token)

    # Determines if the given signature token contains a nominal resource.
    # More specifically, a signature token contains a nominal resource if
    #   1) it is a type variable explicitly marked as resource kind.
    #   2) it is a struct that
    #       a) is marked as resource.
    #       b) has a type actual which is a nominal resource.
    #
    # Similar to `SignatureTokenView.kind`, the context is used for looking up struct
    # definitions & type formals.
    # TODO: refactor views so that we get the type formals from self.
    def contains_nominal_resource(self, type_formals: List[Kind]) -> bool :
        if self.token.tag == SerializedType.STRUCT:
            (sh_idx, type_arguments) = self.token.struct
            flag = StructHandleView.new(
                self.module,
                self.module.struct_handle_at(sh_idx)).is_nominal_resource()
            if flag:
                return True
            for token in type_arguments:
                if self.__class__.new(self.module, token).contains_nominal_resource(type_formals):
                    return True
            return False
        else:
            return False


    def is_reference(self) -> bool :
        return self.token.is_reference()


    def is_mutable_reference(self) -> bool :
        return self.token.is_mutable_reference()


    def struct_index(self) -> Optional[StructHandleIndex] :
        return self.token.struct_index()

    # If `self` is a struct or reference to a struct, return a normalized representation of this
    # struct type that can be compared across modules
    def normalize_struct(self) -> Optional[StructTag] :
        if self.struct_handle():
            return self.struct_handle().normalize_struct()
        else:
            return None


    # Return the equivalent `SignatureToken` for `self` inside `module`
    def resolve_in_module(self, other_module: ModuleAccess) -> Optional[SignatureToken] :
        if self.struct_handle():
            struct_handle = self.struct_handle()
            # Token contains a struct handle from `self.module`. Need to resolve inside
            # `other_module`. We do this by normalizing the struct in `self.token`, then
            # searching for the normalized representation inside `other_module`
            # TODO: do we need to resolve `self.token`'s type actuals
            type_actuals = []
            handle_idx = ModuleView.new(other_module).resolve_struct(struct_handle.normalize_struct())
            if handle_idx:
                return SignatureToken.Struct(handle_idx, type_actuals)
            else:
                return None
        else:
            return deepcopy(self.token)


    def __str__(self):
        s = self.normalize_struct()
        if s is not None:
            if self.is_reference():
                return f"&{s}"
            elif self.is_mutable_reference():
                return f"{s}"
            else:
                return s.__str__()
        else:
            return self.token.__str__()


