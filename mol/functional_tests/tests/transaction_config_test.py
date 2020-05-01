from mol.functional_tests.common import strip
from mol.functional_tests.config.globl import Config as GlobalConfig
from mol.functional_tests.config.transaction import is_new_transaction, Config, Entry
from mol.functional_tests.errors import *
from mol.functional_tests.tests.mod import parse_each_line_as
from mol.functional_tests.tests.global_config_test import parse_and_build_config as parse_and_build_global_config
import pytest


def test_parse_simple_positive():
    for s in [
        "//!no-run:",
        "//! no-run: verifier",
        "//! no-run: compiler, verifier, runtime",
        "//! sender: alice",
        "//! sender:foobar42",
        "//! sender :alice",
        "//! sender:foobar42",
        "//! sender\t:\tfoobar42",
        "//!\nsender\n:\nfoobar42",
    ]:
        e = Entry.from_str(s)
        print(e)




def test_parse_simple_negative():
    for s in ["//!", "//! ", "//! garbage", "//! sender:"]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


def test_parse_args():
    for s in [
        "//! args:",
        "//! args: 12",
        "//! args: 0xdeadbeef",
        "//! args: b\"AA\"",
        "//! args: {{bob}}",
        "//! args: 1, 2, 3, 4",
        "//! args: 1, 0x12, {{bob}}, {{alice}},",
    ]:
        Entry.from_str(s)


    for s in [
        "//!args",
        "//! args: 42xx",
        "//! args: bob",
        "//! args: \"\"",
    ]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)



def test_parse_max_gas():
    for s in ["//! max-gas:77", "//!max-gas:0", "//! max-gas:  123"]:
        Entry.from_str(s)

    for s in ["//!max-gas:", "//!max-gas:abc", "//!max-gas: 123, 45"]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


def test_parse_sequence_number():
    for s in [
        "//! sequence-number:77",
        "//!sequence-number:0",
        "//! sequence-number:  123",
    ]:
        Entry.from_str(s)

    for s in [
        "//!sequence-number:",
        "//!sequence-number:abc",
        "//!sequence-number: 123, 45",
    ]:
        with pytest.raises(Exception) as excinfo:
            Entry.from_str(s)


#     //! TODO: "//!sequence-number: 123 45" is currently parsed as 12345.
#     //! This is because we remove all the spaces before parsing.
#     //! Rewrite the parser to handle this case properly.
# }


def test_parse_new_transaction():
    assert(is_new_transaction("//! new-transaction"))
    assert(is_new_transaction("//!new-transaction "))
    assert(not is_new_transaction("//"))
    assert(not is_new_transaction("//! new transaction"))
    assert(not is_new_transaction("//! transaction"))


def parse_and_build_config(global_config: GlobalConfig, s: str) -> Config:
    return Config.build(global_config, parse_each_line_as(s, Entry))


def test_build_transaction_config_1():
    globl = parse_and_build_global_config("")

    parse_and_build_config(globl, """
        //! no-run: verifier, runtime
        //! sender: default
        //! args: 1, 2, 3
    """)




def test_build_transaction_config_2():
    globl = parse_and_build_global_config("""
        //! account: bob
        //! account: alice
    """)

    parse_and_build_config(globl, """
        //! sender: alice
        //! args: {{bob}}, {{alice}}
    """)




def test_build_transaction_config_3():
    globl = parse_and_build_global_config("""
        //! account: alice
    """)

    with pytest.raises(Exception) as excinfo:
        parse_and_build_config(globl, "//! args: {{bob}}")

