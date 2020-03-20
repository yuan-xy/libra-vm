from functional_tests.checker import *
from functional_tests.checker.directives import *
from functional_tests.common import Sp
from functional_tests.errors import *
from libra.rustlib import assert_equal, usize
import pytest

def check_sp(sp: Sp, d: Directive, start: usize, end: usize) -> None:
    assert_equal(sp.start, start)
    assert_equal(sp.end, end)
    assert_equal(sp.inner, d)



def test_check_one() -> None:
    directives = Directive.parse_line("// check: abc")
    assert(directives.__len__() == 1)
    check_sp(directives[0], Directive(Directive.Check, "abc"), 10, 13)



def test_not_one() -> None:
    directives = Directive.parse_line("// not: abc")
    assert(directives.__len__() == 1)
    check_sp(directives[0], Directive(Directive.Not, "abc"), 8, 11)



def test_check_two() -> None:
    directives = Directive.parse_line("// check: abc  f")
    assert(directives.__len__() == 2)

    check_sp(directives[0], Directive(Directive.Check, "abc"), 10, 13)
    check_sp(directives[1], Directive(Directive.Check, "f"), 15, 16)



def test_not_two() -> None:
    directives = Directive.parse_line("// not: abc  f")
    assert(directives.__len__() == 2)

    check_sp(directives[0], Directive(Directive.Not, "abc"), 8, 11)
    check_sp(directives[1], Directive(Directive.Not, "f"), 13, 14)



def test_compact() -> None:
    directives = Directive.parse_line("//not:a b c")
    assert(directives.__len__() == 3)

    check_sp(directives[0], Directive(Directive.Not, "a"), 6, 7)
    check_sp(directives[1], Directive(Directive.Not, "b"), 8, 9)
    check_sp(directives[2], Directive(Directive.Not, "c"), 10, 11)



def test_check_quoted() -> None:
    tokens = tokenize_patterns(r"""// check: "abc  def\\\t\n\r\"" """)
    assert len(tokens) == 6
    directives = Directive.parse_line(r"""// check: "abc  def\\\t\n\r\"" """)
    assert(directives.__len__() == 1)

    check_sp(
        directives[0],
        Directive(Directive.Check, "abc  def\\\t\n\r\""),
        10,
        30,
    )



def test_check_two_quoted() -> None:
    directives = Directive.parse_line(r"""// check: " " "\"" """)
    assert(directives.__len__() == 2)

    check_sp(directives[0], Directive(Directive.Check, " "), 10, 13)
    check_sp(directives[1], Directive(Directive.Check, "\""), 14, 18)



def test_check_quoted_and_unquoted_mixed() -> None:
    directives = Directive.parse_line(r"""// check: " " abc  "" """)
    assert(directives.__len__() == 3)

    check_sp(directives[0], Directive(Directive.Check, " "), 10, 13)
    check_sp(directives[1], Directive(Directive.Check, "abc"), 14, 17)
    check_sp(directives[2], Directive(Directive.Check, ""), 19, 21)



def test_check_empty() -> None:
    with pytest.raises(Exception) as excinfo:
        Directive.parse_line("// check:")



def test_not_empty() -> None:
    with pytest.raises(Exception) as excinfo:
        Directive.parse_line("// not:")
