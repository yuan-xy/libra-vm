from __future__ import annotations
from functional_tests.checker.directives import Directive
from functional_tests.evaluator import EvaluationLog, EvaluationOutput
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping
from enum import Enum, IntEnum
from canoser import Uint64

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
#     #         check: 5
#     #     group 3:
#     #         not: 6
#
# Then in order, we take one group at a time and match it against the evaluation log.
# Recall that the (stringified) evaluation log is essentially a list of string entries
# that look like this:
#
#     # [1] abc de
#     # [2] foo 3
#     # [3] 5 bar 6
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
#     # [3] 5 bar 6
#     #       ^^^ ^
#     #       |   not 6
#     #       check: bar
#     # [5] 7
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


# A group consisting of 0 or more negative directives followed by an optional positive directive.
# An Aho-Corasick automaton is used for efficient matching.
# struct MatcherGroup<D> {
#     directives: List[(usize, D)],
#     automaton: AhoCorasick,
# }

# A group match consisting of the type of the match (p/n), the id of the matched directive and
# the start and end locations of the text matched (in bytes).
# struct GroupMatch {
#     is_positive: bool,
#     directive_id: usize,
#     start: usize,
#     end: usize,
# }

# impl<D: AsRef<Directive>> MatcherGroup<D> {
#     # Find the earliest place where any directive in the group is matched.
#     def match_earliest(self, s: &str) -> Optional[GroupMatch] {
#         self.automaton.earliest_find(s).map(|mat| {
#             pat_id = mat.pattern()
#             directive_id = self.directives[pat_id].0
#             is_positive = self.directives[pat_id].1.is_positive()

#             GroupMatch {
#                 is_positive,
#                 directive_id,
#                 start: mat.start(),
#                 end: mat.end(),
#             }
#         })
#     }
# }

# # Divides the directives into matcher groups and builds an Aho-Corasick automaton for each group.
# def build_matcher_groups<I, D>(directives: I) -> List[MatcherGroup<D]>
# where
#     D: AsRef<Directive>,
#     I: IntoIterator<Item = D>,
# {
#     groups = []
#     buffer = []

#     for (id, d) in directives.into_iter().enumerate() {
#         if d.is_positive() {
#             buffer.push((id, d))
#             groups.push(buffer)
#             buffer = []
#         else:
#             buffer.push((id, d))
#         }
#     }
#     if !buffer.is_empty() {
#         groups.push(buffer)
#     }

#     groups
#         .into_iter()
#         .map(|directives| {
#             automaton = AhoCorasickBuilder.new()
#                 .dfa(True)
#                 .build(directives.iter().map(|(_, d)| d.pattern_str()))
#             MatcherGroup {
#                 directives,
#                 automaton,
#             }
#         })
#         .collect()
# }

# # An iterator that steps through all matches produced by the given matcher groups
# # against the (stringified) log.
# struct MatchIterator<'a, D, S> {
#     text: &'a [S],
#     matcher_groups: &'a [MatcherGroup<D>],
#     cur_entry_id: usize,
#     cur_entry_offset: usize,
#     cur_group_id: usize,
# }

# impl<'a, D, S> MatchIterator<'a, D, S>
# where
#     D: AsRef<Directive>,
#     S: AsRef<str>,
# {
#     def new(matcher_groups: &'a [MatcherGroup<D>], text: &'a [S]) -> Self {
#         Self {
#             text,
#             matcher_groups,
#             cur_entry_id: 0,
#             cur_entry_offset: 0,
#             cur_group_id: 0,
#         }
#     }
# }

# impl<'a, D, S> Iterator for MatchIterator<'a, D, S>
# where
#     D: AsRef<Directive>,
#     S: AsRef<str>,
# {
#     type Item = (bool, Match)

#     def next(self) -> Optional[Self.Item] {
#         if self.cur_entry_id >= self.text.__len__() || self.cur_group_id >= self.matcher_groups.__len__() {
#             return None
#         }

#         cur_group = self.matcher_groups[self.cur_group_id]
#         while self.cur_entry_id < self.text.__len__() {
#             cur_entry = self.text[self.cur_entry_id]
#             cur_text_fragment = &cur_entry[self.cur_entry_offset..]

#             match cur_group.match_earliest(cur_text_fragment) {
#                 Some(gm) => {
#                     m = Match {
#                         pat_id: gm.directive_id,
#                         entry_id: self.cur_entry_id,
#                         start: gm.start + self.cur_entry_offset,
#                         end: gm.end + self.cur_entry_offset,
#                     }
#                     self.cur_group_id += 1
#                     self.cur_entry_offset = m.end
#                     if self.cur_entry_offset >= cur_entry.__len__() {
#                         self.cur_entry_id += 1
#                         self.cur_entry_offset = 0
#                     }
#                     return Some((gm.is_positive, m))
#                 }
#                 None => {
#                     self.cur_entry_id += 1
#                     self.cur_entry_offset = 0
#                 }
#             }
#         }
#         None
#     }
# }


# A single match consisting of the index of the log entry, the start location and the end location (in bytes).
@dataclass
class Match:
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
class MatchError:
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

# The status of a match.
# Can be either success or failure with errors.
@dataclass
class MatchStatus:
    tag: int
    value: List[MatchError]

    vSuccess = 1
    vFailure = 2

    @classmethod
    def Success(cls):
        return cls(cls.vSuccess, None)

    @classmethod
    def Failure(cls, v):
        return cls(cls.vFailure, v)



    def is_success(self) -> bool:
        return self.tag == MatchStatus.vSuccess


    def is_failure(self) -> bool:
        return self.tag == MatchStatus.vFailure


# The result of matching the directives against the evaluation log.
@dataclass
class MatchResult:
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

    for d in directives:
        # for i, pd in matches:
        #     if pd == d.inner and cur == i:
        #         cur += 1    #if directive is the same, new match should match next text.
        ret = lambda0(d)
        if ret is not None:
            return ret

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

