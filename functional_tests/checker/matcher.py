from __future__ import annotations
from functional_tests.checker.directives import Directive
from functional_tests.evaluator import EvaluationLog, EvaluationOutput
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping
from enum import Enum, IntEnum
from canoser import Uint64
from move_core import JsonPrintable

# This module implements a matcher that checks if an evaluation log matches the
# patterns specified by a list of directives.
#
# The directives first get divided into groups, where each group consists of
# 0 or more negative directives, followed by an optional positive directive.
#
#     # Directives:
#     #     not: 1
#     #     not: 2
#     #     check: 3
#     #     not: 4
#     #     check: bar
#     #     not : 6
#
#     # Groups:
#     #     group 1:
#     #         not: 1
#     #         not: 2
#     #         check: 3
#     #     group 2:
#     #         not: 4
#     #         check: bar
#     #     group 3:
#     #         not: 6
#
# Then in order, we take one group at a time and match it against the evaluation log.
# Recall that the (stringified) evaluation log is essentially a list of string entries
# that look like this:
#
#     # [1] abc de
#     # [2] foo 3
#     # [3] bar 6
#     # [4] 7
#
# For each group, we find the earliest place in the current entry where any of the
# directives matches.
#     - If the matched directive is negative, abort and report error.
#     - If the matched direcrive is positive, move on to the next group and start a
#       new match right after the last matched location.
#     - If no match is found, retry the current group with the next entry in the log.
#
# Example matches:
#
#     # [1] abc de
#     # [2] foo 3
#     #         ^
#     #         check: 3
#     # [3] bar 6
#     #     ^^^ ^
#     #     |   not 6
#     #     check: bar
#     # [4] 7
#
# Note: the group matching procedure above requires searching for multiple string patterns
# simultatenously. Right now this is implemented using the Aho-Corasick algorithm, achieving
# an overall time complexity of O(n), where n is the length of the log + the total length of
# the string patterns in the directives.
#
# In order for the match to succeed, it is required that:
#     1) All positive directives are matched.
#     2) No negative directives are matched.
#     3) All error entries in the log are matched.
#
# The example above would fail with a negative match.


# A single match consisting of the index of the log entry, the start location and the end location (in bytes).
@dataclass
class Match(JsonPrintable):
    pat_id: usize
    entry_id: usize
    start: usize
    end: usize


class METag(IntEnum):
    vNegativeMatch = 1 #(Match),
    vUnmatchedDirectives = 2 #(List[usize]),
    vUnmatchedErrors = 3 #(List[usize]),

# A match error.
@dataclass
class MatchError(JsonPrintable):
    tag: METag
    value: Any


    @classmethod
    def NegativeMatch(cls, v):
        return cls(METag.vNegativeMatch, v)

    @classmethod
    def UnmatchedDirectives(cls, v):
        return cls(METag.vUnmatchedDirectives, v)

    @classmethod
    def UnmatchedErrors(cls, v):
        return cls(METag.vUnmatchedErrors, v)


class MatchStatusTag(IntEnum):
    vSuccess = 1
    vFailure = 2

# The status of a match.
# Can be either success or failure with errors.
@dataclass
class MatchStatus(JsonPrintable):
    tag: MatchStatusTag
    value: List[MatchError]



    @classmethod
    def Success(cls):
        return cls(MatchStatusTag.vSuccess, None)

    @classmethod
    def Failure(cls, v):
        return cls(MatchStatusTag.vFailure, v)



    def is_success(self) -> bool:
        return self.tag == MatchStatusTag.vSuccess


    def is_failure(self) -> bool:
        return self.tag == MatchStatusTag.vFailure


# The result of matching the directives against the evaluation log.
@dataclass
class MatchResult(JsonPrintable):
    status: MatchStatus
    text: List[str]
    matches: List[Match]


    def is_success(self) -> bool:
        return self.status.is_success()


    def is_failure(self) -> bool:
        return self.status.is_failure()


# Matches the directives against the evaluation log.
def match_output(log: EvaluationLog, directives: List[Directive]) -> MatchResult:
    # Convert each entry of the evaluation log into a string, which will be later matched against.
    text = [x.__str__() for x in log.outputs]
    cur = 0
    cur_pos = (cur, 0)
    matches = []

    def lambda0(sp):
        nonlocal cur
        nonlocal cur_pos
        d = sp.inner
        for i in range(cur, len(text)):
            if cur_pos[0] == i:
                from_idx = cur_pos[1]
            else:
                from_idx = 0
            pos = text[i][from_idx:].find(d.value)
            if pos != -1:
                if d.is_positive():
                    cur = i
                    cur_pos = (cur, from_idx + pos + len(d.value))
                    print(cur_pos)
                    matches.append((i, d))
                    return None
                else:
                    return MatchResult(
                        MatchStatus.Failure([MatchError.NegativeMatch((i, d))]),
                        text[i],
                        matches,
                    )
        if d.is_positive():
            return MatchResult(
                        MatchStatus.Failure([MatchError.UnmatchedDirectives(d)]),
                        text[i],
                        matches,
                    )

    dit_arr = []
    cur_dit_arr = []
    for sp in directives:
        cur_dit_arr.append(sp)
        if sp.inner.is_positive():
            dit_arr.append(cur_dit_arr)
            cur_dit_arr = []

    for arr in dit_arr:
        assert arr[-1].inner.is_positive()
        ret = lambda0(arr[-1]) #last is positive
        if ret is not None:
            return ret

        for sp in arr[0:-1]:   #negative
            d = sp.inner
            pos = text[cur].find(d.value)
            if pos != -1:
                return MatchResult(
                    MatchStatus.Failure([MatchError.NegativeMatch((cur, d))]),
                    text[cur],
                    matches,
                )

    matche_ids = [i for (i, d) in matches]
    for i, x in enumerate(log.outputs):
        if x.is_error():
            if i not in matche_ids:
                return MatchResult(
                        MatchStatus.Failure([MatchError.UnmatchedErrors([i])]),
                        text[i],
                        matches,
                    )

    # Return the result.
    return MatchResult(
        MatchStatus.Success(),
        text,
        matches,
    )

