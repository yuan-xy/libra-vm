from __future__ import annotations
from libra import AccessPath, Address, AccountConfig
from libra.event import EventHandle
from libra.transaction import (
    RawTransaction, Script, SignedTransaction, TransactionArgument, TransactionPayload
)
from mol.move_vm.types.loaded_data import StructDef, Type
from mol.move_vm.types.values import Struct as VMStruct
from mol.move_vm.types.values import Value
from libra.crypto.ed25519 import *
from libra.transaction.authenticator import AuthenticationKey
from mol.vm_genesis.lib import GENESIS_KEYPAIR
from mol.move_vm.types.identifier import create_access_path
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
        privkey, pubkey = generate_keypair("rng")
        return cls.with_keypair(privkey, pubkey)


    # Creates a new account with the given keypair.
    #
    # Like with [`Account.new`], the account returned by this constructor is a purely logical
    # entity.
    @classmethod
    def with_keypair(cls, privkey: Ed25519PrivateKey, pubkey: Ed25519PublicKey) -> Account:
        addr = AuthenticationKey.ed25519(pubkey).derived_address()
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
    def make_account_access_path(self) -> AccessPath:
        return create_access_path(self.addr, AccountConfig.account_struct_tag())

    def make_balance_access_path(self) -> AccessPath:
        return create_access_path(self.addr, AccountConfig.account_balance_struct_tag())


    # Changes the keys for this account to the provided ones.
    def rotate_key(self, privkey: Ed25519PrivateKey, pubkey: Ed25519PublicKey):
        self.privkey = privkey
        self.pubkey = pubkey


    # Computes the authentication key for this account, as stored on the chain.
    #
    # This is the same as the account's address if the keys have never been rotated.
    def auth_key(self) -> bytes:
        return  AuthenticationKey.ed25519(self.pubkey)


    def auth_key_prefix(self) -> bytes:
        return AuthenticationKey.ed25519(self.pubkey).prefix()

    def default(cls) -> Account:
        return cls.new()



def new_event_handle(count: Uint64) -> EventHandle:
    return EventHandle.random_handle(count)

@dataclass
class Balance:
    coin: Uint64

    # Returns the Move Value for the account balance
    def to_value(self) -> Value:
        return Value.struct_(VMStruct.pack([Value.Uint64(self.coin)]))
    

    # Returns the value layout for the account balance
    @classmethod
    def layout(cls) -> StructDef:
        return StructDef.new([Type('U64')])


# Represents an account along with initial state about it.
#
# `AccountData` captures the initial state needed to create accounts for tests.

@dataclass
class AccountData:
    account: e2e_tests.account.Account
    balance: Balance
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
            Balance(balance),
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


    def account_layout() -> StructDef:
        VectorU8 = Type('Vector', Type('U8'))
        return StructDef.new([
            VectorU8,
            Type('Bool'),
            Type('Bool'),
            Type('Struct', StructDef.new([Type('U64'), VectorU8])),
            Type('Struct', StructDef.new([Type('U64'), VectorU8])),
            Type('U64'),
            Type('Struct', StructDef.new([Type('U64')])),
        ])

    # Returns the layout for the LibraAccount.Balance struct
    def balance_layout() -> StructDef:
        return Balance.layout()
    

    # Creates and returns a resource [`Value`] for this data.
    def to_account(self) -> Tuple[Value, Value]:
        # TODO: publish some concept of Account
        balance = self.balance.to_value()
        account = self._to_resource()
        return (account, balance)

    # Creates and returns a resource [`Value`] for this data.
    def _to_resource(self) -> Value:
        # TODO: publish some concept of Account
        #TTODO: why not use Uint64 directly for coin
        return Value.struct_(VMStruct.pack([
            Value.vector_u8(
                AuthenticationKey.ed25519(self.account.pubkey),
            ),
            Value.bool(self.delegated_key_rotation_capability),
            Value.bool(self.delegated_withdrawal_capability),
            Value.struct_(VMStruct.pack([
                Value.Uint64(self.received_events.count),
                Value.vector_u8(self.received_events.key),
            ])),
            Value.struct_(VMStruct.pack([
                Value.Uint64(self.sent_events.count),
                Value.vector_u8(self.sent_events.key),
            ])),
            Value.Uint64(self.sequence_number),
            Value.struct_(VMStruct.pack([Value.Uint64(self.event_generator)])),
        ]))


    # Returns the AccessPath that describes the Account resource instance.
    #
    # Use this to retrieve or publish the Account blob.
    # TODO: plug in the account type
    def make_account_access_path(self) -> AccessPath:
        return self.account.make_account_access_path()

    def make_balance_access_path(self) -> AccessPath:
        return self.account.make_balance_access_path()


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
