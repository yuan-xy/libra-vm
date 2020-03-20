from __future__ import annotations
from functional_tests.common import strip, Sp
from functional_tests.errors import *
from dataclasses import dataclass
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping, Union
from enum import Enum
from canoser import Uint64


# The basic unit of input to the directive parser.
@dataclass
class Token:
    tag: int
    value: str

    String = 1
    QuotedString = 2
    Whitespace = 3

char = str

@dataclass
class Input:
    s: str
    idx: int = -1

    def _next(self):
        if self.idx+1 >= len(self.s):
            return None
        self.idx += 1
        return self.s[self.idx]

    def peek(self):
        if self.idx+1 >= len(self.s):
            return None
        return self.s[self.idx+1]

    def _next_with_idx(self):
        if self.idx+1 >= len(self.s):
            return None
        self.idx += 1
        return (self.idx, self.s[self.idx])

    def peek_with_idx(self):
        if self.idx+1 >= len(self.s):
            return None
        return (self.idx+1, self.s[self.idx+1])

# Find the next token at the beginning of the input char stream.
def next_token(ins: Input) -> Optional[Token]:
    ch = ins._next()
    if ch == '"':
        buffer = ""
        while True:
            ch2 = ins._next()
            if ch2 == '"':
                return Token(Token.QuotedString, buffer)
            elif ch2 == '\\':
                ch3 = ins._next()
                if ch3 == '\\':
                    buffer += '\\'
                elif ch3 == 'n':
                    buffer += '\n'
                elif ch3 == 't':
                    buffer += '\t'
                elif ch3 == 'r':
                    buffer += '\r'
                elif ch3 == '"':
                    buffer += '"'
                elif ch3 is not None:
                    bail("unrecognized escape character \\{}", ch3)
                else:
                    bail("unclosed escape character")
            else:
                buffer += ch2
    elif ch.isspace():
        buffer = ch
        while True:
            peekc = ins.peek()
            if peekc and peekc.isspace():
                buffer += peekc
                ins._next()
            else:
                break
        return Token(Token.Whitespace, buffer)
    elif ch is not None:
        buffer = ch
        while True:
            peekc = ins.peek()
            if peekc == '"' or peekc is None:
                break
            elif peekc.isspace():
                break
            else:
                buffer += peekc
                ins._next()
        return Token(Token.String, buffer)
    else:
        return None


class SpToken(Sp):
    pass


# Split the input string into tokens with spans.
# The tokens will later be used to build directives.
def tokenize_patterns(s: str) -> List[SpToken]:
    ins = Input(s)
    tokens = []
    while True:
        peek = ins.peek_with_idx()
        if peek is None:
            break
        else:
            start = peek[0]

        tok = next_token(ins)
        if tok is None:
            break

        end = ins.peek_with_idx()
        if end is not None:
            end = end[0]
        else:
            end = len(s)

        tokens.append(SpToken(tok, start, end))

    return tokens


class SpDirective(Sp):
    pass


# Specification of an expected text pattern in the output.
#
# There are two types of directives: positive and negative.
# A positive directive means the pattern should match some text in the output,
# while a nagative one considers such match to be an error.
@dataclass
class Directive:
    tag: int
    value: str

    Check = 1
    Not = 2


    # Returns if the directive is a positive pattern.
    def is_positive(self) -> bool:
        return self.tag == Directive.Check

    # Returns if the directive is a negative pattern.
    def is_negative(self) -> bool:
        return self.tag == Directive.Not


    # Returns the pattern of the directive.
    def pattern_str(self) -> str:
        return self.value


    @classmethod
    def try_parse(cls, s: str) -> Optional[List[SpDirective]]:
        try:
            return cls.parse_line(s)
        except:
            return None


    # Parses the line and extracts one or more directives from it.
    @classmethod
    def parse_line(cls, s: str) -> List[SpDirective]:
        # TODO: rewrite how the offset is counted.
        offset = 0

        def trim(s: str):
            nonlocal offset
            it = Input(s)
            while True:
                tp = it._next_with_idx()
                if tp is not None:
                    (idx, c) = tp
                    if not c.isspace():
                        offset += idx
                        return s[idx:]
                else:
                    return s[len(s):]

        def stripm(s: str, pat: str):
            nonlocal offset
            res = strip(s, pat)
            if res is not None:
                offset += pat.__len__()
            return res

        s = stripm(trim(s), "//")
        if s is None:
            bail("directives must start with //")

        s = trim(s)
        sc = stripm(s, "check")
        if sc:
            (s, check) = (sc, True)
        else:
            sn = stripm(s, "not")
            if sn:
                (s, check) = (sn, False)
            else:
                bail("expects 'check' or 'not' after //")

        s = stripm(trim(s), ":")
        if s is None:
            bail("expects ':' after directive name")

        def lambda0(sp):
            inner, start, end = sp.inner, sp.start, sp.end
            if inner.tag == Token.String or inner.tag == Token.QuotedString:
                s = inner.value
                if check:
                    d = Directive(Directive.Check, s)
                else:
                    d = Directive(Directive.Not, s)

                return Sp(d, start + offset, end + offset)
            else:
                bail("unreachable!")
                # return None

        directives = [lambda0(sp) for sp in tokenize_patterns(s) if sp.inner.tag != Token.Whitespace]

        if not directives:
            bail("no directives found in line")

        return directives


    def as_ref(self) -> Directive:
        return self
