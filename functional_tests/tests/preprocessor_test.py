from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.errors import *
from functional_tests.preprocessor import build_transactions, split_input
import pytest


def parse_input(ins: str):
    (config, _x, transactions) = split_input(ins.splitlines())
    config = GlobalConfig.build(config)
    return build_transactions(config, transactions)



def test_parse_input_no_transactions():
    with pytest.raises(Exception) as excinfo:
        parse_input("")


def test_parse_input_no_transactions_with_config():
    with pytest.raises(Exception) as excinfo:
        parse_input("//! no-run: verifier")




def test_parse_input_nothing_before_first_empty_transaction():
    parse_input(r"""
        //! new-transaction
        main() {}
    """)



def test_parse_input_config_before_first_empty_transaction():
    with pytest.raises(Exception) as excinfo:
        parse_input(r"""
            //! no-run: runtime
            //! new-transaction
            main() {}
        """)


def test_parse_inputs():
    result = parse_input(r"""
            main() {}
            //! new-transaction
            //! expiration-time: 12345
            //! no-run: verifier
            test
            // check: EXECUTED
            //! new-transaction
            main() {}
            // check: EXECUTED
        """)
    assert len(result) == 3


def test_parse_input_empty_transaction():
    with pytest.raises(Exception) as excinfo:
        result = parse_input(r"""
            main() {}

            //! new-transaction

            //! new-transaction
            main() {}
        """)




def test_parse_input_empty_transaction_with_config():
    with pytest.raises(Exception) as excinfo:
        result = parse_input(r"""
            main() {}

            //! new-transaction
            //! sender: default

            //! new-transaction
            main() {}
        """)
