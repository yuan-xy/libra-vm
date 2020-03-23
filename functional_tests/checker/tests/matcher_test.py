from functional_tests.checker import *
from functional_tests.evaluator import *
import pytest
from libra.rustlib import assert_equal


def logs(arr):
    ret = EvaluationLog([])
    for e in arr:
        ret.append(e)
    return ret


class DummyError(str):
    pass


def err(s):
    return EvaluationOutput.Error(DummyError(s.__str__()))


def dirs(arr):
    directives = []
    for s in arr:
        directives.extend([sp for sp in Directive.parse_line(s)])
    return directives


def test_match_check_simple_1():
    log = logs([err("foo bar")])
    directives = dirs(["// check: \"o b\""])
    res = match_output(log, directives)
    assert(res.is_success())
    assert_equal(res.matches.__len__(), 1)



def test_match_check_simple_2():
    log = logs([err("foo bar")])
    directives = dirs(["// check: foo bar"])
    res = match_output(log, directives)
    assert(res.is_success())
    assert_equal(res.matches.__len__(), 2)



def test_match_not():
    log = logs([err("foo"), err("bar"), err("baz")])
    directives = dirs(["// check: bar", "// not: baz"])
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 1)



def test_match_mixed_1():
    log = logs([err("foo bar"), err("abc")])
    directives = dirs(["// check: foo", "// not: rab", "// check: abc"])
    res = match_output(log, directives)
    assert(res.is_success())
    assert_equal(res.matches.__len__(), 2)



def test_match_mixed_2():
    log = logs([err("abc de"), err("foo 3"), err("5 bar 6"), err("7")])
    print(f"{log}")
    directives = dirs([
        "// not: 1",
        "// not: 2",
        "// check: 3",
        "// not: 4",
        "// check: 5",
        "// not: 6"
    ])
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 2)



def test_unmatched_directives_1():
    log = logs([err("foo bar")])
    directives = dirs(["// check: foo", "// check: bbar"])
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 1)



def test_unmatched_directives_2():
    log = logs([err("foo bar"), err("baz")])
    directives = dirs(["// check: oo", "// check: baz", "// check: zz"])
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 2)



def test_unmatched_errors_1():
    log = logs([err("foo")])
    directives: List[Directive] = []
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 0)



def test_unmatched_errors_2():
    log = logs([err("foo"), err("bar")])
    directives = dirs(["// check: bar"])
    res = match_output(log, directives)
    assert(res.is_failure())
    assert_equal(res.matches.__len__(), 1)

