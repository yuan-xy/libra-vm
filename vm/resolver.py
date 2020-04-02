from __future__ import annotations
from vm import ModuleAccess, SerializedType
from vm.file_format import (
    AddressPoolIndex, FunctionSignature, IdentifierIndex, ModuleHandle, ModuleHandleIndex,
    SignatureToken, StructHandle, StructHandleIndex
    )
from libra.account_address import Address
from move_core.types.identifier import Identifier
from libra.vm_error import StatusCode, VMStatus
from typing import List, Set, Optional, Tuple, Mapping, Any
from dataclasses import dataclass
import abc
import traceback
from copy import deepcopy

# This module implements a resolver for importing a SignatureToken defined in one module into
# another. This functionaliy is used in verify_module_dependencies and verify_script_dependencies.


# Resolution context for importing types
@dataclass
class Resolver:
    address_map: Mapping[Address, AddressPoolIndex]
    identifier_map: Mapping[Identifier, IdentifierIndex]
    module_handle_map: Mapping[ModuleHandle, ModuleHandleIndex]
    struct_handle_map: Mapping[StructHandle, StructHandleIndex]


    # create a new instance of Resolver for module
    @classmethod
    def new(cls, module: ModuleAccess) -> Resolver:
        address_map = {}
        for (idx, address) in enumerate(module.address_pool()):
            address_map[address] = AddressPoolIndex(idx)

        identifier_map = {}
        for (idx, name) in enumerate(module.identifiers()):
            identifier_map[name] = IdentifierIndex(idx)

        module_handle_map = {}
        for (idx, module_hadndle) in enumerate(module.module_handles()):
            module_handle_map[module_hadndle] = ModuleHandleIndex(idx)

        struct_handle_map = {}
        for (idx, struct_handle) in enumerate(module.struct_handles()):
            struct_handle_map[struct_handle] = StructHandleIndex(idx)

        return cls(
            address_map,
            identifier_map,
            module_handle_map,
            struct_handle_map,
        )


    # given a signature token in dependency, construct an equivalent signature token in the
    # context of this resolver and return it; return an error if resolution fails
    def import_signature_token(
        self,
        dependency: ModuleAccess,
        sig_token: SignatureToken,
    ) -> SignatureToken:
        if sig_token.tag == SerializedType.STRUCT:
            (sh_idx, types) = sig_token.struct
            struct_handle = dependency.struct_handle_at(sh_idx)
            defining_module_handle = dependency.module_handle_at(struct_handle.module)
            defining_module_address = dependency.address_at(defining_module_handle.address)
            defining_module_name = dependency.identifier_at(defining_module_handle.name)
            try:
                local_module_handle = ModuleHandle(
                    address = self.address_map[defining_module_address],
                    name = self.identifier_map[defining_module_name],
                )
                struct_name = dependency.identifier_at(struct_handle.name)
                local_struct_handle = StructHandle(
                    module = self.module_handle_map[local_module_handle],
                    name = self.identifier_map[struct_name],
                    is_nominal_resource = struct_handle.is_nominal_resource,
                    type_formals = deepcopy(struct_handle.type_formals),
                )
                tuple2 = (self.struct_handle_map[local_struct_handle],
                        [self.import_signature_token(dependency, t) for t in types] )
                return SignatureToken(sig_token.tag, tuple2)
            except Exception as err:
                traceback.print_exc()
                raise VMException(VMStatus(StatusCode.TYPE_RESOLUTION_FAILURE))
        elif sig_token.tag == SerializedType.REFERENCE or sig_token.tag == SerializedType.MUTABLE_REFERENCE:
            sub_sig_token = sig_token.reference
            return SignatureToken(
                sig_token.tag,
                reference = self.import_signature_token(dependency, sub_sig_token),
            )
        elif sig_token.tag == SerializedType.VECTOR:
            ty = sig_token.vector_type
            vector_type = self.import_signature_token(dependency, ty)
            return SignatureToken(sig_token.tag, vector_type = vector_type)
        else:
            return deepcopy(sig_token)



    # given a function signature in dependency, construct an equivalent function signature in the
    # context of this resolver and return it; return an error if resolution fails
    def import_function_signature(
        self,
        dependency: ModuleAccess,
        func_sig: FunctionSignature,
    ) -> FunctionSignature:
        return_types = []
        arg_types = []
        for e in func_sig.return_types:
            return_types.append(self.import_signature_token(dependency, e))

        for e in func_sig.arg_types:
            arg_types.append(self.import_signature_token(dependency, e))

        return FunctionSignature(
            return_types,
            arg_types,
            deepcopy(func_sig.type_formals),
        )

