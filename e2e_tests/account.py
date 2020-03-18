from __future__ import annotations
from libra import AccessPath, Address, AccountConfig
from libra.event import EventHandle
from libra.transaction import (
    RawTransaction, Script, SignedTransaction, TransactionArgument, TransactionPayload
)
from move_vm.types.loaded_data import StructDef, Type
from move_vm.types.values import Struct, Value
from libra.crypto.ed25519 import *
from vm_genesis.lib import GENESIS_KEYPAIR
from libra_vm.runtime.identifier import create_access_path
from dataclasses import dataclass
from typing import List, Optional, Mapping


# Test infrastructure for modeling Libra accounts.


# TTL is 86400s. Initial time was set to 0.
DEFAULT_EXPIRATION_TIME: Uint64 = 40_000

# Details about a Libra account.
#
# Tests will typically create a set of `Account` instances to run transactions on. This type
# encodes the logic to operate on and verify operations on any Libra account.
@dataclass
class Account:
    addr: Address
    # The current private key for this account.
    privkey: Ed25519PrivateKey
    # The current public key for this account.
    pubkey: Ed25519PublicKey


    # Creates a new account in memory.
    #
    # The account returned by this constructor is a purely logical entity, meaning that it does
    # not automatically get added to the Libra store. To add an account to the store, use
    # [`AccountData`] instances with
    # [`FakeExecutor.add_account_data`][crate.executor.FakeExecutor.add_account_data].
    # This function returns distinct values upon every call.
    @classmethod
    def new(cls) -> Account:
        # replace `rng` by None (making the function deterministic) and watch the
        # functional_tests fail!
        privk, pubk = generate_keypair("rng")
        return cls.with_keypair(privkey, pubkey)


    # Creates a new account with the given keypair.
    #
    # Like with [`Account.new`], the account returned by this constructor is a purely logical
    # entity.
    @classmethod
    def with_keypair(cls, privkey: Ed25519PrivateKey, pubkey: Ed25519PublicKey) -> Account:
        addr = Address.from_public_key(pubkey)
        return cls(
            addr,
            privkey,
            pubkey,
        )

    # Creates a new account in memory representing an account created in the genesis transaction.
    #
    # The address will be [`address`], which should be an address for a genesis account and
    # the account will use [`GENESIS_KEYPAIR`][struct@GENESIS_KEYPAIR] as its keypair.
    @classmethod
    def new_genesis_account(cls, address: Address) -> Account:
        return Account(address, GENESIS_KEYPAIR[0], GENESIS_KEYPAIR[1])


    # Creates a new account representing the association in memory.
    #
    # The address will be [`association_address`][account_config.association_address], and
    # the account will use [`GENESIS_KEYPAIR`][struct@GENESIS_KEYPAIR] as its keypair.
    @classmethod
    def new_association(cls) -> Account:
        return cls.new_genesis_account(AccountConfig.association_address_bytes())


    # Returns the address of the account. This is a hash of the public key the account was created
    # with.
    #
    # The address does not change if the account's [keys are rotated][Account.rotate_key].
    def address(self) -> Address:
        return self.addr


    # Returns the AccessPath that describes the Account resource instance.
    #
    # Use this to retrieve or publish the Account blob.
    # TODO: plug in the account type
    def make_access_path(self) -> AccessPath:
        # TODO: we need a way to get the type (StructDef) of the Account in place
        return create_access_path(self.addr, AccountConfig.account_struct_tag())


    # Changes the keys for this account to the provided ones.
    def rotate_key(self, privkey: Ed25519PrivateKey, pubkey: Ed25519PublicKey):
        self.privkey = privkey
        self.pubkey = pubkey


    # Computes the authentication key for this account, as stored on the chain.
    #
    # This is the same as the account's address if the keys have never been rotated.
    def auth_key(self) -> bytes:
        return Address.from_public_key(self.pubkey)


    # Returns a [`SignedTransaction`] with a payload and this account as the sender.
    #
    # This is the most generic way to create a transaction for testing.
    # Max gas amount and gas unit price are ignored for WriteSet transactions.
    def create_user_txn(
        self,
        payload: TransactionPayload,
        sequence_number: Uint64,
        max_gas_amount: Uint64,
        gas_unit_price: Uint64,
    ) -> SignedTransaction:
        if payload.WriteSet:
            writeset = payload.value
            raw_txn = RawTransaction.new_change_set(self.address(), sequence_number, writeset)
        elif payload.Module:
            module = payload.value
            raw_txn = RawTransaction.new_module(
                self.address(),
                sequence_number,
                module,
                max_gas_amount,
                gas_unit_price,
                DEFAULT_EXPIRATION_TIME,
            )
        elif payload.Script:
            script = payload.value
            raw_txn = RawTransaction.new_script(
                self.address(),
                sequence_number,
                script,
                max_gas_amount,
                gas_unit_price,
                Duration.from_secs(DEFAULT_EXPIRATION_TIME),
            )

        return raw_txn.sign(self.privkey, self.pubkey).into_inner()


    # Returns a [`SignedTransaction`] with the arguments defined in `args` and this account as
    # the sender.
    def create_signed_txn_with_args(
        self,
        program: bytes,
        args: List[TransactionArgument],
        sequence_number: Uint64,
        max_gas_amount: Uint64,
        gas_unit_price: Uint64,
    ) -> SignedTransaction:
        return self.create_signed_txn_impl(
            self.address(),
            TransactionPayload('Script', Script(program, args)),
            sequence_number,
            max_gas_amount,
            gas_unit_price,
        )


    # Returns a [`SignedTransaction`] with the arguments defined in `args` and a custom sender.
    #
    # The transaction is signed with the key corresponding to this account, not the custom sender.
    def create_signed_txn_with_args_and_sender(
        self,
        sender: Address,
        program: bytes,
        args: List[TransactionArgument],
        sequence_number: Uint64,
        max_gas_amount: Uint64,
        gas_unit_price: Uint64,
    ) -> SignedTransaction:
        return self.create_signed_txn_impl(
            sender,
            TransactionPayload('Script', Script(program, args)),
            sequence_number,
            max_gas_amount,
            gas_unit_price,
        )


    # Returns a [`SignedTransaction`] with the arguments defined in `args` and a custom sender.
    #
    # The transaction is signed with the key corresponding to this account, not the custom sender.
    def create_signed_txn_impl(
        self,
        sender: Address,
        program: TransactionPayload,
        sequence_number: Uint64,
        max_gas_amount: Uint64,
        gas_unit_price: Uint64,
    ) -> SignedTransaction:
        return RawTransaction(
            sender,
            sequence_number,
            program,
            max_gas_amount,
            gas_unit_price,
            # TTL is 86400s. Initial time was set to 0.
            DEFAULT_EXPIRATION_TIME,
        ).sign(self.privkey, self.pubkey).into_inner()


    def default(cls) -> Account:
        return cls.new()



def new_event_handle(count: Uint64) -> EventHandle:
    return EventHandle.random_handle(count)


# Represents an account along with initial state about it.
#
# `AccountData` captures the initial state needed to create accounts for tests.

@dataclass
class AccountData:
    account: e2e_tests.account.Account
    balance: Uint64
    sequence_number: Uint64
    delegated_key_rotation_capability: bool
    delegated_withdrawal_capability: bool
    sent_events: EventHandle
    received_events: EventHandle
    event_generator: Uint64


    # Creates a new `AccountData` with a new account.
    #
    # Most tests will want to use this constructor.
    @classmethod
    def new(cls, balance: Uint64, sequence_number: Uint64) -> AccountData:
        return cls.with_account(Account.new(), balance, sequence_number)


    # Creates a new `AccountData` with the provided account.
    @classmethod
    def with_account(cls, account: Account, balance: Uint64, sequence_number: Uint64) -> AccountData:
        return cls.with_account_and_event_counts(account, balance, sequence_number, 0, 0, False, False)


    # Creates a new `AccountData` with the provided account.
    @classmethod
    def with_keypair(cls,
        privkey: Ed25519PrivateKey,
        pubkey: Ed25519PublicKey,
        balance: Uint64,
        sequence_number: Uint64,
    ) -> AccountData:
        account = Account.with_keypair(privkey, pubkey)
        return cls.with_account(account, balance, sequence_number)


    # Creates a new `AccountData` with custom parameters.
    @classmethod
    def with_account_and_event_counts(cls,
        account: Account,
        balance: Uint64,
        sequence_number: Uint64,
        sent_events_count: Uint64,
        received_events_count: Uint64,
        delegated_key_rotation_capability: bool,
        delegated_withdrawal_capability: bool,
    ) -> AccountData:
        return cls(
            account,
            balance,
            sequence_number,
            delegated_key_rotation_capability,
            delegated_withdrawal_capability,
            new_event_handle(sent_events_count),
            new_event_handle(received_events_count),
            2,
        )


    # Changes the keys for this account to the provided ones.
    def rotate_key(self, privkey: Ed25519PrivateKey, pubkey: Ed25519PublicKey):
        self.account.rotate_key(privkey, pubkey)


    def layout() -> StructDef:
        return StructDef.new([
            Type.ByteArray,
            Type.Struct(StructDef.new([Type.U64])),
            Type.Bool,
            Type.Bool,
            Type.Struct(StructDef.new([Type.U64, Type.ByteArray])),
            Type.Struct(StructDef.new([Type.U64, Type.ByteArray])),
            Type.U64,
            Type.Struct(StructDef.new([Type.U64])),
        ])


    # Creates and returns a resource [`Value`] for this data.
    def to_resource(self) -> Value:
        # TODO: publish some concept of Account
        coin = Value.struct_(Struct.pack([Value.Uint64(self.balance)]))
        Value.struct_(Struct.pack([
            Value.byte_array(ByteArray.new(
                Address.from_public_key(self.account.pubkey),
            )),
            coin,
            Value.bool(self.delegated_key_rotation_capability),
            Value.bool(self.delegated_withdrawal_capability),
            Value.struct_(Struct.pack([
                Value.Uint64(self.received_events.count()),
                Value.byte_array(ByteArray.new(self.received_events.key())),
            ])),
            Value.struct_(Struct.pack([
                Value.Uint64(self.sent_events.count()),
                Value.byte_array(ByteArray.new(self.sent_events.key())),
            ])),
            Value.Uint64(self.sequence_number),
            Value.struct_(Struct.pack([Value.Uint64(self.event_generator)])),
        ]))


    # Returns the AccessPath that describes the Account resource instance.
    #
    # Use this to retrieve or publish the Account blob.
    # TODO: plug in the account type
    def make_access_path(self) -> AccessPath:
        return self.account.make_access_path()


    # Returns the address of the account. This is a hash of the public key the account was created
    # with.
    #
    # The address does not change if the account's [keys are rotated][AccountData.rotate_key].
    def address(self) -> Address:
        return self.account.address()


    # Converts this data into an `Account` instance.
    def into_account(self) -> Account:
        return self.account




    # Returns the unique key for this sent events stream.
    def sent_events_key(self) -> bytes:
        return self.sent_events.key


    # Returns the initial sent events count.
    def sent_events_count(self) -> Uint64:
        return self.sent_events.count


    # Returns the unique key for this received events stream.
    def received_events_key(self) -> bytes:
        return self.received_events.key


    # Returns the initial received events count.
    def received_events_count(self) -> Uint64:
        return self.received_events.count
