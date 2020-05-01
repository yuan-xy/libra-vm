from __future__ import annotations
from mol.functional_tests.common import strip
from mol.functional_tests.config.block_metadata import build_block_metadata, is_new_block, Entry
from mol.functional_tests.config.globl import Config as GlobalConfig
from mol.functional_tests.errors import *
from mol.functional_tests.tests.mod import parse_each_line_as
from mol.functional_tests.tests.global_config_test import parse_and_build_config as parse_and_build_global_config
from libra.block_metadata import BlockMetadata
import pytest

def test_parse_simple_positive():
    for s in [
        "//! proposer: alice",
        "//! proposer\t:\tfoobar42",
        "//!\nproposer\n:\nfoobar42",
    ]:
        e = Entry.from_str(s)
        print(e)


def test_parse_simple_negative():
    for s in ["//!", "//! ", "//! sender: alice", "//! proposer:"]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


def test_parse_timestamp():
    for s in [
        "//! block-time:77",
        "//!block-time:0",
        "//! block-time:  123",
    ]:
        e = Entry.from_str(s)
        print(e)

    for s in [
        "//!block-time:",
        "//!block-time:abc",
        "//!block-time: 123, 45",
    ]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


def test_parse_new_transaction():
    assert(is_new_block("//! block-prologue"))
    assert(is_new_block("//!block-prologue "))
    assert(not is_new_block("//"))
    assert(not is_new_block("//! new block"))
    assert(not is_new_block("//! block"))


def parse_and_build_config(global_config: GlobalConfig, s: str) -> BlockMetadata:
    return build_block_metadata(global_config, parse_each_line_as(s, Entry))


def test_build_transaction_config_1():
    globl = parse_and_build_global_config("""
        //! account: alice
    """)

    x = parse_and_build_config(globl, """
        //! proposer: alice
        //! block-time: 6
    """)
    assert x.timestamp_usecs == 6
    assert globl.accounts['alice'].address() == x.proposer

    with pytest.raises(Exception) as excinfo:
        parse_and_build_config(globl, """
            //! proposer: alice
        """)

    with pytest.raises(Exception) as excinfo:
        parse_and_build_config(globl, """
            //! block-time: 6
        """)



def test_build_transaction_config_3():
    globl = parse_and_build_global_config("""
        //! account: alice
    """)

    with pytest.raises(Exception) as excinfo:
        parse_and_build_config(globl, """
            //! proposer: bob
            //! block-time: 6
        """)

