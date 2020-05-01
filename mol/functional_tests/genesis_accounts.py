from __future__ import annotations
from mol.e2e_tests.account import Account
from libra.account_config import AccountConfig
from dataclasses import dataclass
from libra.rustlib import usize
from typing import Any, List, Optional, Mapping

# These are special-cased since they are generated in genesis, and therefore we don't want
# their account states to be generated.
ASSOCIATION_NAME = "association"
FEE_NAME = "fees"

def make_genesis_accounts() -> Mapping[str, Account]:
    m = {} #BTreeMap.new()
    m[ASSOCIATION_NAME] = Account.new_association()
    m[FEE_NAME] = \
        Account.new_genesis_account(AccountConfig.transaction_fee_address_bytes())
    return m

