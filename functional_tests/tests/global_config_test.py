from __future__ import annotations
from functional_tests.config.globl import Config, Entry
from functional_tests.errors import *
from functional_tests.tests.mod import parse_each_line_as
import pytest
from libra.rustlib import assert_equal

def test_parse_account_positive():
    for s in [
        "//! account: alice",
        "//!account: bob",
        "//! account: bob, 100",
        "//!account:alice,",
        "//!   account :alice,1, 2",
        "//! account: bob, 0, 0",
        "//!    account : bob, 0, 0",
        "//!    account     :bob,   0,  0",
        "//!\naccount\n:bob,\n0,\n0",
        "//!\taccount\t:bob,\t0,\t0",
        "//! account: alice, 1000, 0, validator",
    ]:
        e = Entry.from_str(s)
        print(e)


def test_parse_account_negative():
    for s in [
        "//! account:",
        "//! account",
        "//! account: alice, 1, 2, validator, 4",
    ]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


# Parses each line in the given input as an entry and build global config.
def parse_and_build_config(s: str) -> Config:
    return Config.build(parse_each_line_as(s, Entry))


def test_build_global_config_2():
    config = parse_and_build_config("")
    assert(config.accounts.__len__() == 1)
    assert("default" in config.accounts)



def test_build_global_config_1():
    config = parse_and_build_config("""
        //! account: Alice,
        //! account: bob, 2000, 10
    """)

    assert(config.accounts.__len__() == 3)
    assert("default" in config.accounts)
    assert("alice" in config.accounts)
    bob = config.accounts["bob"]
    assert(bob.balance.coin == 2000)
    assert(bob.sequence_number == 10)



def test_build_global_config_3():
    with pytest.raises(Exception) as excinfo:
        parse_and_build_config("""
            //! account: bob
            //! account: BOB
        """)



def test_build_global_config_4():
    config = parse_and_build_config("//! account: default, 50,")
    assert_equal(config.accounts.__len__(), 1)
    default = config.accounts["default"]
    assert_equal(default.balance.coin, 50)
