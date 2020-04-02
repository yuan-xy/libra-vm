from libra.access_path import AccessPath, Accesses
from libra.account_address import Address
from libra.language_storage import ResourceKey, StructTag, TypeTag
from libra_vm.file_format import ModuleAccess
from libra_vm.file_format import StructDefinitionIndex
from typing import List

# A bunch of helper functions to fetch the storage key for move resources and values.


# Get the StructTag for a StructDefinition defined in a published module.
def resource_storage_key(
    module: ModuleAccess,
    idx: StructDefinitionIndex,
    type_params: List[TypeTag],
) -> StructTag:
    resource = module.struct_def_at(idx)
    res_handle = module.struct_handle_at(resource.struct_handle)
    res_module = module.module_handle_at(res_handle.module)
    res_name = module.identifier_at(res_handle.name)
    res_mod_addr = module.address_at(res_module.address)
    res_mod_name = module.identifier_at(res_module.name)
    return StructTag(
        module = res_mod_name,
        address = res_mod_addr,
        name = res_name,
        type_params = type_params,
    )

# Get the AccessPath to a resource stored under `address` with type name `tag`
def create_access_path(address: Address, tag: StructTag) -> AccessPath:
    resource_tag = ResourceKey(address, tag)
    return AccessPath.resource_access_path(resource_tag, Accesses.empty())

