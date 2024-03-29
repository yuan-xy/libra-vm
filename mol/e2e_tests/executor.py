from __future__ import annotations
from mol.e2e_tests.account import Account, AccountData
from mol.e2e_tests.data_store import FakeDataStore, GENESIS_WRITE_SET
from mol.bytecode_verifier import VerifiedModule
from libra_storage.state_view import StateView
from libra import AccessPath, AccountResource
from libra.account_resource import BalanceResource
from libra.language_storage import ModuleId
from libra.transaction import (
    SignedTransaction, Transaction, TransactionOutput, TransactionPayload, TransactionStatus,
    WriteSet
)
from libra.validator_set import ValidatorSet
from libra.vm_error import StatusCode, VMStatus
from libra.block_metadata import BlockMetadata
from libra.hasher import HashValue
from libra.rustlib import ensure, bail, usize
from mol.stdlib import stdlib_modules
from mol.vm import CompiledModule
from mol.vm_genesis.main import rust_validator_set
from mol.vm_genesis.lib import make_placeholder_discovery_set, GENESIS_KEYPAIR, encode_genesis_transaction_with_validator_and_modules
from mol.libra_vm import LibraVM, VMExecutor, VMVerifier
from dataclasses import dataclass
from typing import List, Optional, Mapping, Callable, Tuple
from canoser import Uint64
from enum import Enum
from libra.rustlib import ensure, bail, usize

# Support for running the VM to execute and verify transactions.

class VMPublishingOption(Enum):
    Locked = 0
    # Allow custom scripts, but _not_ custom module publishing
    CustomScripts = 1
    # Allow both custom scripts and custom module publishing
    Open = 2


def test_all_genesis_impl(
    publishing_options: Optional[VMPublishingOption],
    test_fn: Callable[[FakeExecutor], None],
) -> None:
    ws = GENESIS_WRITE_SET
    test_fn(FakeExecutor.from_genesis(ws, publishing_options))


def test_all_genesis_default(test_fn: Callable[[FakeExecutor], None]):
    test_all_genesis_impl(None, test_fn)


def test_all_genesis(
    publishing_options: Optional[VMPublishingOption],
    test_fn: Callable[[FakeExecutor], None],
):
    test_all_genesis_impl(publishing_options, test_fn)



# Provides an environment to run a VM instance.
#
# This class is a mock in-memory implementation of the Libra executor.
@dataclass
class FakeExecutor:
    data_store: FakeDataStore
    block_time: Uint64

    # Creates an executor from a genesis [`WriteSet`].
    @classmethod
    def from_genesis(cls,
        write_set: WriteSet,
    ) -> FakeExecutor:
        executor = FakeExecutor(
            FakeDataStore({}),
            0,
        )
        executor.apply_write_set(write_set)
        return executor


    # Creates an executor from the genesis file GENESIS_FILE_LOCATION
    @classmethod
    def from_genesis_file(cls) -> FakeExecutor:
        return cls.from_genesis(GENESIS_WRITE_SET)


    # Creates an executor from the genesis file GENESIS_FILE_LOCATION with script/module
    # publishing options given by `publishing_options`. These can only be either `Open` or
    # `CustomScript`.
    @classmethod
    def from_genesis_with_options(cls, publishing_options: VMPublishingOption) -> FakeExecutor:
        if VMPublishingOption.Locked == publishing_options:
            bail("Whitelisted transactions are not supported as a publishing option")

        return cls.from_genesis(GENESIS_WRITE_SET, publishing_options)


    # Creates an executor in which no genesis state has been applied yet.
    @classmethod
    def no_genesis(cls) -> FakeExecutor:
        return FakeExecutor(
            FakeDataStore.default(),
            0,
        )

    # Creates fresh genesis from the stdlib modules passed in. If none are passed in the staged
    # genesis write set is used.
    @classmethod
    def custom_genesis(cls,
        genesis_modules: Optional[List[VerifiedModule]],
        validator_set: Optional[ValidatorSet],
        publishing_options: VMPublishingOption,
    ) -> FakeExecutor:
        if genesis_modules is None and validator_set is None:
            genesis_write_set = GENESIS_WRITE_SET.raw_txn.payload.value.write_set
        elif validator_set is None:
            genesis_write_set = GENESIS_WRITE_SET.raw_txn.payload.value.write_set
        else:
            discovery_set = make_placeholder_discovery_set(validator_set)
            if genesis_modules:
                stdlib_modules = genesis_modules
            else:
                stdlib_modules = stdlib_modules()

            txn = encode_genesis_transaction_with_validator_and_modules(
                GENESIS_KEYPAIR[0],
                GENESIS_KEYPAIR[1],
                validator_set,
                discovery_set,
                stdlib_modules,
            )
            genesis_write_set = txn.into_inner().payload.value.write_set

        return cls.from_genesis(genesis_write_set)


    # Creates a number of [`Account`] instances all with the same balance and sequence number,
    # and publishes them to this executor's data store.
    def create_accounts(self, size: usize, balance: Uint64, seq_num: Uint64) -> List[Account]:
        accounts: List[Account] = []
        for _i in range(size):
            account_data = AccountData.new(balance, seq_num)
            self.add_account_data(account_data)
            accounts.append(account_data.into_account())

        return accounts


    # Applies a [`WriteSet`] to this executor's data store.
    def apply_write_set(self, write_set: WriteSet):
        self.data_store.add_write_set(write_set)


    # Adds an account to this executor's data store.
    def add_account_data(self, name: str, account_data: AccountData):
        self.data_store.add_account_data(name, account_data)


    # Adds a module to this executor's data store.
    #
    # Does not do any sort of verification on the module.
    def add_module(self, module_id: ModuleId, module: CompiledModule):
        self.data_store.add_module(module_id, module)


    # Reads the resource [`Value`] for an account from this executor's data store.
    def read_account_resource(self, account: Account) -> Optional[AccountResource]:
        ap = account.make_account_access_path()
        data_blob = self.data_store.get(ap)
        return AccountResource.deserialize(data_blob)

    def read_balance_resource(self, account: Account) -> Optional[BalanceResource]:
        ap = account.make_balance_access_path()
        data_blob = self.data_store.get(ap)
        return BalanceResource.deserialize(data_blob)

    def read_account_info(self, account: Account) -> Optional[Tuple[AccountResource, BalanceResource]]:
        return self.read_account_resource(account), self.read_balance_resource(account)


    # Executes the given block of transactions.
    #
    # Typical tests will call this method and check that the output matches what was expected.
    # However, this doesn't apply the results of successful transactions to the data store.
    def execute_block(
        self,
        txn_block: List[SignedTransaction],
    ) -> List[TransactionOutput]:
        return LibraVM.execute_block(
            [Transaction('UserTransaction', x) for x in txn_block],
            self.data_store,
        )


    # Executes the transaction as a singleton block and applies the resulting write set to the
    # data store. Panics if execution fails
    def execute_and_apply(self, transaction: SignedTransaction) -> TransactionOutput:
        outputs = self.execute_block([transaction])
        ensure(outputs.__len__() == 1, "transaction outputs size mismatch")
        output = outputs.pop()
        if output.status.tag == TransactionStatus.Keep:
            status = output.status.vm_status
            self.apply_write_set(output.write_set())
            ensure(
                status.major_status == StatusCode.EXECUTED,
                "transaction failed with {}",
                status
            )
            return output
        else:
            bail("transaction discarded with {}", output),


    def execute_transaction_block(
        self,
        txn_block: List[Transaction],
    ) -> List[TransactionOutput]:
        return LibraVM.execute_block(txn_block, self.data_store)


    def execute_transaction(self, txn: SignedTransaction) -> TransactionOutput:
        txn_block = [txn]
        outputs = self.execute_block(txn_block)
        return outputs.pop()


    # Get the blob for the associated AccessPath
    def read_from_access_path(self, path: AccessPath) -> Optional[bytes]:
        return self.data_store.get(path)


    # Verifies the given transaction by running it through the VM verifier.
    def verify_transaction(self, txn: SignedTransaction) -> Optional[VMStatus]:
        vm = LibraVM.new()
        vm.load_configs(self.get_state_view())
        return vm.validate_transaction(txn, self.data_store)


    def get_state_view(self) -> FakeDataStore:
        return self.data_store


    def new_block(self):
        #TTODO when to call new_block
        breakpoint()
        # validator_address =\
        #     generator.validator_swarm_for_testing(10).validator_set[0].account_address()
        # self.block_time += 1
        # new_block = BlockMetadata.new(
        #     HashValue.zero(),
        #     self.block_time,
        #     {},
        #     validator_address,
        # )
        # self.apply_write_set(
        #     self.execute_transaction_block(
        #         [Transaction.BlockMetadata(new_block)]
        #     ).get(0).write_set()
        # )
