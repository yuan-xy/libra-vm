from __future__ import annotations
from functional_tests.common import strip
from functional_tests.errors import *
from functional_tests.genesis_accounts import make_genesis_accounts
from e2e_tests.account import Account, AccountData
from libra.validator_set import ValidatorSet
from libra.crypto.ed25519 import _generate_keypair_by_private_key
from vm_genesis.main import rust_validator_set
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping
from enum import Enum
from canoser import Uint64

# The config holds the options that define the testing environment.
# A config entry starts with "#", differentiating it from a directive.

# unit: microlibra
DEFAULT_BALANCE = 1_000_000


class Role(Enum):
    # Means that the account is a current validator; its address is in the on-chain validator set
    Validator = 1

    @classmethod
    def from_str(cls, s: str) -> Role:
        if s == "validator":
            return Role.Validator
        else:
            err = format_str("Invalid account role {}", s)
            raise ErrorKind(ErrorKindTag.Other, err)


# Struct that specifies the initial setup of an account.
@dataclass
class AccountDefinition:
    # Name of the account. The name is case insensitive.
    name: String
    # The initial balance of the account.
    balance: Uint64 = DEFAULT_BALANCE
    # The initial sequence number of the account.
    sequence_number: Uint64 = 0
    # Special role this account has in the system (if any)
    role: Optional[Role] = None




# A raw entry extracted from the input. Used to build the global config table.
@dataclass
class Entry:
    # Defines an account that can be used in tests.
    accountDefinition: AccountDefinition


    def is_validator(self) -> bool:
        if self.accountDefinition.role == Role.Validator:
            return True
        else:
            return False


    @classmethod
    def try_parse(cls, s: str) -> Optional[Entry]:
        try:
            return cls.from_str(s)
        except:
            return None

    @classmethod
    def from_str(cls, s: str) -> Entry:
        s = "".join(s.split())
        s = strip(s, "//!")
        if not s:
            return None
        s = s.lstrip()
        s = strip(s, "account:")
        if s:
            v = flatten([x.split() for x in s.split(",")])

            if not v or v.__len__() > 4:
                raise ErrorKind(ErrorKindTag.Other,
                    "config 'account' takes 1 to 4 parameters",
                )

            if len(v) > 1:
                balance = Uint64.int_safe(v[1])
            else:
                balance = DEFAULT_BALANCE

            if len(v) > 2:
                sequence_number = Uint64.int_safe(v[2])
            else:
                sequence_number = 0

            if len(v) > 3:
                role = Role.from_str(v[3])
            else:
                role = None

            return Entry(AccountDefinition(
                v[0],
                balance,
                sequence_number,
                role,
            ))
        else:
            raise ErrorKind(ErrorKindTag.Other, format_str("failed to parse '{}' as global config entry", s))


# A table of options either shared by all transactions or used to define the testing environment.
@dataclass
class Config:
    # A map from account names to account data
    accounts: Mapping[str, AccountData] #BTreeMap
    genesis_accounts: Mapping[str, Account]
    # The validator set after genesis
    validator_set: ValidatorSet

    @classmethod
    def build(cls, entries: List[Entry]) -> Config:
        accounts = {} #BTreeMap.new()
        validator_accounts = len([x for x in entries if x.is_validator()])

        # generate a validator set with |validator_accounts| validators
        if validator_accounts > 0:
            assert validator_accounts <= 10
            validator_set = rust_validator_set()[0:validator_accounts]
            validator_keys = {x.account_address: b'\x00'*32 for x in validator_set}

            # swarm = generator.validator_swarm_for_testing(validator_accounts)
            # validator_keys = {} #BTreeMap<_, _>
            # for c in swarm.nodes:
            #     peer_id = c.validator_network.peer_id
            #     account_keypair = c.test.as_mut().account_keypair.as_mut()
            #     privkey = account_keypair.take_private()
            #     validator_keys[peer_id] = privkey

            (validator_keys, validator_set) = (validator_keys, validator_set)
        else:
            (validator_keys, validator_set) = ({}, [])


        # initialize the keys of validator entries with the validator set
        # enhance type of config to contain a validator set, use it to initialize genesis
        for entry in entries:
            ddef = entry.accountDefinition
            if entry.is_validator():
                validator_accounts -= 1
                # privkey = validator_keys.iter().nth(validator_accounts)[1]
                privkey = bytes([validator_accounts] * 32)
                privkey, pubkey = _generate_keypair_by_private_key(privkey)
                account_data = AccountData.with_keypair(
                    privkey,
                    pubkey,
                    ddef.balance,
                    ddef.sequence_number,
                )
                account_data.account.addr = validator_set[validator_accounts].account_address
            else:
                account_data = AccountData.new(
                    ddef.balance,
                    ddef.sequence_number,
                )

            name = ddef.name.lower()
            if name not in accounts:
                accounts[name] = account_data
            else:
                raise ErrorKind(ErrorKindTag.Other, format_str(
                        "already has account '{}'",
                        ddef.name,
                    ))

        if "default" not in accounts:
            accounts["default"] = AccountData.new(
                DEFAULT_BALANCE,
                0,
            )

        return Config(
            accounts,
            make_genesis_accounts(),
            validator_set,
        )


    def get_account_for_name(self, name: str) -> Account:
        if name in self.accounts:
            account_data = self.accounts[name]
            return account_data.account
        elif name in self.genesis_accounts:
            return self.genesis_accounts[name]
        else:
            raise ErrorKind(ErrorKindTag.Other, format_str("account '{}' does not exist", name))
