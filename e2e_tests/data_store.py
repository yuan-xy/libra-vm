from __future__ import annotations
from e2e_tests.account import AccountData
from libra_storage.state_view import StateView
from libra.access_path import AccessPath
from libra.language_storage import ModuleId
from libra.transaction import Transaction, TransactionPayload
from libra.transaction.write_set import WriteOp, WriteSet
from move_vm.types.values import Struct

from libra_vm.errors import *
from libra_vm import CompiledModule
from libra_vm.runtime.data_cache import RemoteCache
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Mapping


# Support for mocking the Libra data store.

def load_genesis(path: str) -> WriteSet:
    from os.path import join, abspath, dirname
    curdir = dirname(__file__)
    file = join(curdir, path)
    bytecode_bytes = Path(file).read_bytes()
    txn = Transaction.deserialize(bytecode_bytes)
    return txn.value
    if tnx.UserTransaction:
        txn = txn.value
        if txn.payload.WriteSet:
            ws = txn.payload.value
            return ws.write_set
    bail("Expected writeset txn in genesis txn")


# The write set encoded in the genesis transaction.
GENESIS_WRITE_SET = load_genesis("../vm_genesis/genesis/genesis.blob")

# An in-memory implementation of [`StateView`] and [`RemoteCache`] for the VM.
#
# Tests use this to set up state, and pass in a reference to the cache whenever a `StateView` or
# `RemoteCache` is needed.
@dataclass
class FakeDataStore(StateView, RemoteCache):
    data: Mapping[AccessPath, bytes]


    # Adds a [`WriteSet`] to this data store.
    def add_write_set(self, write_set: WriteSet):
        for (access_path, write_op) in write_set.write_set:
            if write_op.Value:
                blob = write_op.value
                self.set(access_path, blob)
            elif write_op.Deletion:
                self.remove(access_path)
            else:
                bail("unreachable!")

    # Sets a (key, value) pair within this data store.
    #
    # Returns the previous data if the key was occupied.
    def set(self, access_path: AccessPath, data_blob: bytes) -> Optional[bytes]:
        if access_path in self.data:
            ret = self.data[access_path]
            self.data[access_path] = data_blob
            return ret
        else:
            self.data[access_path] = data_blob
            return None


    # Deletes a key from this data store.
    #
    # Returns the previous data if the key was occupied.
    def remove(self, access_path: AccessPath) -> Optional[bytes]:
        if access_path in self.data:
            return self.data.pop(access_path)
        else:
            return None


    # Adds an [`AccountData`] to this data store.
    def add_account_data(self, account_data: AccountData):
        v = account_data.to_resource()
        struct = v.value_as(Struct)
        blob = struct.simple_serialize(AccountData.layout())
        # res = Value.simple_deserialize(blob, Type('Struct',AccountData.layout()))
        # assert res.__str__() == v.__str__()
        self.set(account_data.make_access_path(), blob)


    # Adds a [`CompiledModule`] to this data store.
    #
    # Does not do any sort of verification on the module.
    def add_module(self, module_id: ModuleId, module: CompiledModule):
        access_path = module_id.into()
        blob = module.serialize()
        self.set(access_path, blob)


# This is used by the `execute_block` API.
# TODO: only the "sync" get is implemented
# impl StateView for FakeDataStore {
    def get(self, access_path: AccessPath) -> Optional[bytes]:
        if access_path in self.data:
            return self.data[access_path]
        else:
            return None

    def multi_get(self, _access_paths: List[AccessPath]) -> List[Optional[bytes]]:
        bail("unimplemented")

    def is_genesis(self) -> bool:
        return not self.data


# This is used by the `process_transaction` API.
# impl RemoteCache for FakeDataStore {
    # def get(self, access_path: AccessPath) -> Optional[bytes]:
    #     return StateView.get(self, access_path)


