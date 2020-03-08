from __future__ import annotations
from canoser import DelegateT
import re

# An identifier is the name of an entity (module, resource, function, etc) in Move.
#
# A valid identifier consists of an ASCII string which satisfies any of the conditions:
#
# * The first character is a letter and the remaining characters are letters, digits or
#   underscores.
# * The first character is an underscore, and there is at least one further letter, digit or
#   underscore.
#
# The spec for allowed identifiers is similar to Rust's spec
# ([as of version 1.38](https://doc.rust-lang.org/1.38.0/reference/identifiers.html)).
#
# Allowed identifiers are currently restricted to ASCII due to unresolved issues with Unicode
# normalization. See [Rust issue #55467](https://github.com/rust-lang/rust/issues/55467) and the
# associated RFC for some discussion. Unicode identifiers may eventually be supported once these
# issues are worked out.
#
# This module only determines allowed identifiers at the bytecode level. Move source code will
# likely be more restrictive than even this, with a "raw identifier" escape hatch similar to
# Rust's `r#` identifiers.


# Describes what identifiers are allowed.
#
# For now this is deliberately restrictive -- we would like to evolve this in the future.
# TODO: "<SELF>" is coded as an exception. It should be removed once CompiledScript goes away.
def is_valid(s: str) -> bool:
    def is_first_char(ch: char) -> bool:
        od = ord(ch)
        if '_' == ch:
            return True
        if od >= ord('a') and od <= ord('z'):
            return True
        if od >= ord('A') and od <= ord('Z'):
            return True
        return False
    def is_underscore_alpha_or_digit(ch: char) -> bool:
        od = ord(ch)
        if '_' == ch:
            return True
        if od >= ord('a') and od <= ord('z'):
            return True
        if od >= ord('A') and od <= ord('Z'):
            return True
        if od >= ord('0') and od <= ord('9'):
            return True
        return False

    if s == "<SELF>":
        return True

    if s == "_":
        return False

    if not s:
        return False

    if not is_first_char(s[0]):
        return False

    for ch in s[1:]:
        if not is_underscore_alpha_or_digit(ch):
            return False

    return True


# A regex describing what identifiers are allowed. Used for proptests.
# TODO: "<SELF>" is coded as an exception. It should be removed once CompiledScript goes away.
#ALLOWED_IDENTIFIERS = r"(?:[a-zA-Z][a-zA-Z0-9_]*)|(?:_[a-zA-Z0-9_]+)|(?:<SELF>)"


class Identifier(DelegateT):
    """
    An identifier is the name of an entity (module, resource, function, etc) in Move.

    Among other things, identifiers are used to:
    * specify keys for lookups in storage
    * do cross-module lookups while executing transactions
    """
    delegate_type = str


    # Creates a new `Identifier` instance.
    def new(s: str) -> str:
        if not is_valid(s):
            bail("Invalid identifier '{}'", s)
        return s

Identifier.is_valid = is_valid

# A borrowed identifier.
#
# For more details, see the module level documentation.
class IdentStr(DelegateT):
    delegate_type = str


    def new(s: str) -> str:
        if not is_valid(s):
            bail("Invalid IdentStr '{}'", s)
        return s

IdentStr.is_valid = is_valid
