from __future__ import annotations
from functional_tests.common import strip
from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.errors import *
from functional_tests.tests.mod import parse_each_line_as
from libra import HashValue, Address
from libra.block_metadata import BlockMetadata
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping, Union
from enum import Enum
from canoser import Uint64
from mol.move_core import JsonPrintable


@dataclass
class Entry(JsonPrintable):
    tag: int
    value: Union[str, Uint64]

    Proposer = 1
    Timestamp = 2

    @classmethod
    def from_str(cls, s: str) -> Entry:
        s = "".join(s.split())
        s = strip(s, "//!").lstrip()
        ps = strip(s, "proposer:")
        if ps is not None:
            if ps.strip() == '':
                raise ErrorKind(ErrorKindTag.Other ,"sender cannot be empty")
            else:
                return Entry(Entry.Proposer, ps)

        bs = strip(s, "block-time:").strip()
        if bs:
            return Entry(Entry.Timestamp, Uint64.int_safe(bs))

        raise ErrorKind(ErrorKindTag.Other ,format_str(
            "failed to parse '{}' as transaction config entry",
            s
        ))

    @classmethod
    def try_parse(cls, s: str) -> Optional[Entry]:
        if s.startswith("//!"):
            return cls.from_str(s)
        else:
            return None


# Checks whether a line denotes the start of a new transaction.
def is_new_block(s: str) -> bool:
    s = s.strip()
    if not s.startswith("//!"):
        return False

    return s[3:].lstrip() == "block-prologue"


def build_block_metadata(config: GlobalConfig, entries: List[Entry]) -> BlockMetadata:
    timestamp = None
    proposer = None
    for entry in entries:
        if entry.tag == Entry.Proposer:
            s = entry.value
            proposer = config.get_account_for_name(s).address()
        elif entry.tag == Entry.Timestamp:
            timestamp = entry.value
        else:
            bail("unreachable!")

    if timestamp and proposer:
        # TODO: Add parser for hash value and vote maps.
        return BlockMetadata(
            b'\x00' * HashValue.LENGTH,
            0,
            timestamp,
            [],
            proposer,
        )
    else:
        raise ErrorKind.Other("Cannot generate block metadata")
