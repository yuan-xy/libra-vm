from __future__ import annotations
from libra_storage.state_view import StateView
from libra.access_path import AccessPath
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus
from libra.transaction.write_set import WriteOp, WriteSet, WriteSetMut
from move_vm.types.loaded_data import StructDef, Type
from move_vm.types.values import GlobalValue, Value
from vm.vm_exception import VMException
from vm.errors import *
from typing import List, Optional, Mapping
from dataclasses import dataclass
from copy import deepcopy
import abc
import traceback
import logging

logger = logging.getLogger(__name__)

# Scratchpad for on chain values during the execution.

# The wrapper around the StateVersionView for the block.
# It keeps track of the value that have been changed during execution of a block.
# It's effectively the write set for the block.
@dataclass
class BlockDataCache:
    data_view: StateView
    # TODO: an AccessPath corresponds to a top level resource but that may not be the
    # case moving forward, so we need to review this.
    # Also need to relate this to a ResourceKey.
    data_map: Mapping[AccessPath, bytes] #BtreeMap

    @classmethod
    def new(cls, data_view: StateView) -> BlockDataCache:
        return BlockDataCache(data_view, {})


    def get(self, access_path: AccessPath, tryload=False) -> Optional[bytes]:
        if access_path in self.data_map:
            return deepcopy(self.data_map[access_path])
        else:
            ret = self.data_view.get(access_path)
            if ret is not None:
                return ret
            else:
                if not tryload:
                    logger.critical("[VM] Error getting data from storage for {}", access_path)
                    raise VMException(VMStatus(StatusCode.STORAGE_ERROR))


    def push_write_set(self, write_set: WriteSet):
        for (ap, write_op) in write_set.write_set:
            if write_op.Value:
                self.data_map[ap] = deepcopy(write_op.value)
            elif write_op.Deletion:
                # breakpoint()
                if ap in self.data_map:
                    self.data_map.pop(ap)
            else:
                bail("unreachable!")


    def is_genesis(self) -> bool:
        return self.data_view.is_genesis() and not self.data_map


# Trait for the StateVersionView or a mock implementation of the remote cache.
# Unit and integration tests should use this to mock implementations of "storage"
class RemoteCache(abc.ABC):
    @abc.abstractmethod
    def get(self, access_path: AccessPath) -> Optional[bytes]:
        pass


@dataclass
class RemoteStorage(RemoteCache):
    state_store: StateView

    def get(self, access_path: AccessPath) -> Optional[bytes]:
        return self.state_store.get(access_path)


# Global cache for a transaction.
# Materializes Values from the RemoteCache and keeps an Rc to them.
# It also implements the opcodes that talk to storage and gives the proper guarantees of
# reference lifetime.
# Dirty objects are serialized and returned in make_write_set
@dataclass
class TransactionDataCache:
    # TODO: an AccessPath corresponds to a top level resource but that may not be the
    # case moving forward, so we need to review this.
    # Also need to relate this to a ResourceKey.
    data_map: Mapping[AccessPath, Optional[Tuple[StructDef, GlobalValue]]]
    module_map: Mapping[ModuleId, bytes]
    data_cache: RemoteCache


    @classmethod
    def new(cls, data_cache: RemoteCache) -> TransactionDataCache:
        return TransactionDataCache({}, {}, data_cache)


    def exists_module(self, m: ModuleId) -> bool:
        if m in self.module_map:
            return True
        else:
            ap = AccessPath.code_access_path(m)
            try:
                return self.data_cache.get(ap, tryload=True) is not None
            except Exception:
                return False


    def load_module(self, module: ModuleId) -> bytes:
        if module in self.module_map:
            return self.module_map[module]
        else:
            ap = AccessPath.code_access_path(module)
            ret = self.data_cache.get(ap)
            if ret is not None:
                return ret
            else:
                raise VMException(VMStatus(StatusCode.LINKER_ERROR))


    def publish_module(self, m: ModuleId, b: bytes):
        self.module_map[m] = b


    def publish_resource(
        self,
        ap: AccessPath,
        g: Tuple[StructDef, GlobalValue],
    ):
        self.data_map[deepcopy(ap)] = g


    # Retrieve data from the local cache or loads it from the remote cache into the local cache.
    # All operations on the global data are based on this API and they all load the data
    # into the cache.
    # TODO: this may not be the most efficient model because we always load data into the
    # cache even when that would not be strictly needed. Review once we have the whole story
    # working
    def load_data(
        self,
        ap: AccessPath,
        sdef: StructDef,
        tryload: bool = False
    ) -> Optional[Tuple[StructDef, GlobalValue]]:
        if not ap in self.data_map:
            try:
                blob = self.data_cache.get(ap, tryload)
            except Exception as err:
                if tryload:
                    return None
                else:
                    traceback.print_exc()
                    # breakpoint()
                    raise VMException(vm_error(Location(), StatusCode.MISSING_DATA).with_message(err.__str__()))

            if blob is None:
                if tryload:
                    return None
                else:
                    raise VMException(vm_error(Location(), StatusCode.MISSING_DATA))

            try:
                res = Value.simple_deserialize(blob, Type('Struct', sdef))
                gr = GlobalValue.new(res)
                self.data_map[ap] = (sdef, gr)
            except Exception:
                breakpoint()
                raise

        return self.data_map[ap]


    def load_data_then_move(
        self,
        ap: AccessPath,
        sdef: StructDef,
    ) -> Optional[Tuple[StructDef, GlobalValue]]:
        ret = self.load_data(ap, sdef)
        self.data_map[ap] = None # will be marked WriteOp('Deletion') in make_write_set
        return ret


    # Make a write set from the updated (dirty, deleted) global resources along with
    # to-be-published modules.
    # Consume the TransactionDataCache and must be called at the end of a transaction.
    # This also ends up checking that reference count around global resources is correct
    # at the end of the transactions (all ReleaseRef are properly called)
    def make_write_set(self) -> WriteSet:
        if self.data_map.__len__() + self.module_map.__len__() > usize.max_value:
            raise VMException(vm_error(Location(), StatusCode.INVALID_DATA))

        sorted_ws: Mapping[AccessPath, WriteOp] = {}

        data_map = self.data_map
        self.data_map = {}

        for idx, (key, global_val) in enumerate(data_map.items()):
            if global_val is not None:
                (layout, global_val) = global_val
                if not global_val.is_clean():
                    # into_owned_struct will check if all references are properly released
                    # at the end of a transaction
                    data = global_val.into_owned_struct()
                    blob = data.simple_serialize(layout)
                    sorted_ws[key] = WriteOp('Value', blob)
            else:
                sorted_ws[key] = WriteOp('Deletion')

        module_map = self.module_map
        self.module_map = {}
        for (module_id, module) in module_map.items():
            ap = AccessPath.code_access_path(module_id)
            sorted_ws[ap] = WriteOp('Value', module)

        write_set = WriteSetMut([])
        for idx, (key, value) in enumerate(sorted(sorted_ws.items())):
            write_set.write_set.append((key, value))

        try:
            return write_set.freeze()
        except Exception:
            raise VMException(vm_error(Location(), StatusCode.DATA_FORMAT_ERROR))


    # Flush out the cache and restart from a clean state
    def clear(self):
        self.data_map.clear()
        self.module_map.clear()

