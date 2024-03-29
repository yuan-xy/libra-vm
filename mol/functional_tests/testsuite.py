from __future__ import annotations

from typing import List, Tuple

from mol.functional_tests.checker import *
from mol.functional_tests.compiler import Compiler
from mol.functional_tests.config.globl import Config as GlobalConfig
from mol.functional_tests.evaluator import eeval
from mol.functional_tests.preprocessor import build_transactions, split_input
from pathlib import Path
from libra.rustlib import bail, usize

char = str

def at_most_n_chars(s: List[char], n: usize) -> str:
    if len(s) > n:
        return s[0:n] + "..."
    else:
        return s


def at_most_n_before_and_m_after(
    s: str,
    n: usize,
    start: usize,
    end: usize,
    m: usize,
) -> Tuple[str, str, str]:
    before = s[0:start]
    if len(before) > n:
        before = before[start-n: start]

    matched = s[start:end]
    after = at_most_n_chars(s[end:], m)

    return (before, matched, after)


def pretty_mode() -> bool:
    return False
    # pretty = env_var("PRETTY")
    # pretty == "1" || pretty == "True"


# Runs all tests under the test/testsuite directory.
def functional_tests(
    compiler: Compiler,
    path: str,
) -> None:
    ins =Path(path).read_text()

    lines: List[str] = ins.splitlines()

    (config, directives, transactions) = split_input(lines)
    config = GlobalConfig.build(config)
    commands = build_transactions(config, transactions)

    log = eeval(config, compiler, commands, path)
    res = match_output(log, directives)

    if res.status.is_success():
        return
    else:
        # print(log.outputs[-2])
        # print(f"len(directives):{len(directives)} , len(res.matches):{len(res.matches)}")
        errs: List[MatchError] = res.status.value
        # [print(x) for x in directives]
        # [print(x) for x in res.matches]
        bail(errs.__str__())
