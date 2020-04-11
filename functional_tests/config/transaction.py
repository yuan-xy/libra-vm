from __future__ import annotations
from functional_tests.common import strip
from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.errors import *
from functional_tests.lib import Stage
from e2e_tests.account import Account, AccountData
from libra.transaction import TransactionArgument
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping, Union
from enum import Enum
from canoser import Uint64
from move_core import JsonPrintable

# A partially parsed transaction argument.
@dataclass
class Argument(JsonPrintable):
    tag: int
    value: Union[str, TransactionArgument]

    AddressOf = 1
    SelfContained = 2

    @classmethod
    def from_str(cls, s: str) -> Argument:
        try:
            arg = TransactionArgument.parse_as_transaction_argument(s)
            return cls(cls.SelfContained, arg)
        except TypeError as err:
            print(err)
            pass

        if s.startswith("{{") and s.endswith("}}"):
            return cls(cls.AddressOf, s[2:-2])

        raise ErrorKind(ErrorKindTag.Other, format_str("failed to parse '{}' as argument", s))



# A raw entry extracted from the input. Used to build a transaction config table.
@dataclass
class Entry(JsonPrintable):
    tag: int
    value: Any

    DisableStages = 1 #(List[Stage]),
    Sender = 2 #(String),
    Arguments = 3 #(List[Argument]),
    MaxGas = 4 #(Uint64),
    GasPrice = 5 #(Uint64),
    SequenceNumber = 6 #(Uint64),
    ExpirationTime = 7 #(Uint64),

    @classmethod
    def from_str(cls, s: str) -> Entry:
        s = "".join(s.split())
        s = strip(s, "//!").lstrip()

        sender = strip(s, "sender:")
        if sender is not None:
            if not sender:
                raise ErrorKind.Other("sender cannot be empty")
            return Entry(Entry.Sender, sender.lower())


        args = strip(s, "args:")
        if args is not None:
            res = [x.strip() for x in args.split(',')]
            res = [Argument.from_str(x) for x in res if x]
            return Entry(Entry.Arguments, res)

        norun = strip(s, "no-run:")
        if norun is not None:
            res = [x.strip() for x in norun.split(',')]
            res = [Stage.from_str(x) for x in res if x]
            return Entry(Entry.DisableStages, res)

        maxgas = strip(s, "max-gas:")
        if maxgas is not None:
            return Entry(Entry.MaxGas, Uint64.int_safe(maxgas))

        seq = strip(s, "sequence-number:")
        if seq is not None:
            return Entry(Entry.SequenceNumber, Uint64.int_safe(seq))

        exptime = strip(s, "expiration-time:")
        if exptime is not None:
            return Entry(Entry.ExpirationTime, Uint64.int_safe(exptime))

        raise ErrorKind.Other(format_str(
            "failed to parse '{}' as transaction config entry",
            s
        ))

    @classmethod
    def try_parse(cls, s: str) -> Optional[Entry]:
        try:
            return cls.from_str(s)
        except:
            return None


# Checks whether a line denotes the start of a new transaction.
def is_new_transaction(s: str) -> bool:
    s = s.strip()
    if not s.startswith("//!"):
        return False

    return s[3:].lstrip() == "new-transaction"


# A table of options specific to one transaction, fine tweaking how the transaction
# is handled by the testing infra.
@dataclass
class Config(JsonPrintable):
    disabled_stages: Set[Stage] #btreeset
    sender: Account
    args: List[TransactionArgument]
    max_gas: Optional[Uint64]
    gas_price: Optional[Uint64]
    sequence_number: Optional[Uint64]
    expiration_time: Optional[Uint64]


    # Builds a transaction config table from raw entries.
    @classmethod
    def build(cls, config: GlobalConfig, entries: List[Entry]) -> Config:
        disabled_stages = set() #BTreeSet.new()
        sender = None
        args = None
        max_gas = None
        gas_price = None
        sequence_number = None
        expiration_time = None

        for entry in entries:
            if entry.tag == Entry.Sender:
                if sender is None:
                    sender = config.get_account_for_name(entry.value)
                else:
                    raise ErrorKind.Other("sender already set")

            elif entry.tag == Entry.Arguments:
                if args is None:
                    def lambda0(arg):
                        if arg.tag == Argument.AddressOf:
                            return TransactionArgument('Address',
                                config.get_account_for_name(arg.value).address(),
                            )
                        else:
                            return arg.value
                    args = [lambda0(arg) for arg in entry.value]
                else:
                    raise ErrorKind.Other("arguments already set")

            elif entry.tag == Entry.DisableStages:
                for stage in entry.value:
                    if stage in disabled_stages:
                        raise ErrorKind.Other(format_str(
                            "duplicate stage '{}' in black list",
                            stage
                        ))
                    else:
                        disabled_stages.add(stage)

            elif entry.tag == Entry.MaxGas:
                if max_gas is None:
                    max_gas = entry.value
                else:
                    raise ErrorKind.Other("max_gas already set")
            elif entry.tag == Entry.GasPrice:
                if gas_price is None:
                    gas_price = entry.value
                else:
                    raise ErrorKind.Other("gas_price already set")
            elif entry.tag == Entry.SequenceNumber:
                if sequence_number is None:
                    sequence_number = entry.value
                else:
                    raise ErrorKind.Other("sequence_number already set")
            elif entry.tag == Entry.ExpirationTime:
                if expiration_time is None:
                    expiration_time = entry.value
                else:
                    raise ErrorKind.Other("expiration_time already set")
            else:
                bail("unreachable!")

        if sender is None:
            sender = config.accounts.get("default").account
        if args is None:
            args = []

        return cls(
            disabled_stages,
            sender,
            args,
            max_gas,
            gas_price,
            sequence_number,
            expiration_time,
        )


    def is_stage_disabled(self, stage: Stage) -> bool:
        return stage in self.disabled_stages


