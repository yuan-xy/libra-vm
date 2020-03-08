from __future__ import annotations
from move_core.types.identifier import IdentStr, Identifier
from libra.rustlib import *


def test_valid_identifiers():
    valid_identifiers = [
        "foo",
        "FOO",
        "Foo",
        "foo0",
        "FOO_0",
        "_Foo1",
        "FOO2_",
        "foo_bar_baz",
        "_0",
        "__",
        "____________________",
        # TODO: <SELF> is an exception. It should be removed once CompiledScript goes away.
        "<SELF>",
    ]
    for identifier in valid_identifiers:
        ensure(
            Identifier.is_valid(identifier),
            "Identifier '{}' should be valid",
            identifier
        )


def test_invalid_identifiers():
    invalid_identifiers = [
        "",
        "_",
        "0",
        "01",
        "9876",
        "0foo",
        ":foo",
        "fo\\o",
        "fo/o",
        "foo.",
        "foo-bar",
        "foo\u1f389",
    ]
    for identifier in invalid_identifiers:
        ensure(
            not Identifier.is_valid(identifier),
            "Identifier '{}' should be invalid",
            identifier
        )
