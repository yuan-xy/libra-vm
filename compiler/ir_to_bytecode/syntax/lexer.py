from __future__ import annotations
from compiler.ir_to_bytecode.syntax.parse_error import ParseError, ParseErrorInvalidToken
from move_ir.types.codespan import ByteIndex, Span
from move_ir.types.location import Loc
from enum import Enum, auto
from typing import List, Optional, Tuple
from dataclasses import dataclass

class Tok(Enum):
    EOF = auto()
    AddressValue = auto()
    U8Value = auto()
    U64Value = auto()
    U128Value = auto()
    NameValue = auto()
    NameBeginTyValue = auto()
    DotNameValue = auto()
    ByteArrayValue = auto()
    Exclaim = auto()
    ExclaimEqual = auto()
    Percent = auto()
    Amp = auto()
    AmpAmp = auto()
    AmpMut = auto()
    LParen = auto()
    RParen = auto()
    Star = auto()
    Plus = auto()
    Comma = auto()
    Minus = auto()
    Period = auto()
    Slash = auto()
    Colon = auto()
    ColonEqual = auto()
    Semicolon = auto()
    Less = auto()
    LessEqual = auto()
    LessLess = auto()
    Equal = auto()
    EqualEqual = auto()
    EqualEqualGreater = auto()
    Greater = auto()
    GreaterEqual = auto()
    GreaterGreater = auto()
    Caret = auto()
    Underscore = auto()
    # Abort statement in the Move language
    Abort = auto()
    # Aborts if in the spec language
    AbortsIf = auto()
    Acquires = auto()
    Address = auto()
    As = auto()
    Assert = auto()
    Bool = auto()
    BorrowGlobal = auto()
    BorrowGlobalMut = auto()
    Break = auto()
    Continue = auto()
    Copy = auto()
    Else = auto()
    Ensures = auto()
    Exists = auto()
    FALSE = auto()
    Freeze = auto()
    # Function to get transaction sender in the Move language
    GetTxnSender = auto()
    # Like borrow_global = auto() but for spec language
    Global = auto()
    # Like exists = auto() but for spec language
    GlobalExists = auto()
    ToU8 = auto()
    ToU64 = auto()
    ToU128 = auto()
    If = auto()
    Import = auto()
    # For spec language
    Invariant = auto()
    Let = auto()
    Loop = auto()
    Main = auto()
    Module = auto()
    Modules = auto()
    Move = auto()
    MoveFrom = auto()
    MoveToSender = auto()
    Native = auto()
    Old = auto()
    Public = auto()
    Requires = auto()
    Resource = auto()
    # Return in the specification language
    SpecReturn = auto()
    # Return statement in the Move language
    Return = auto()
    Script = auto()
    Struct = auto()
    SucceedsIf = auto()
    Synthetic = auto()
    TRUE = auto()
    # Transaction sender in the specification language
    TxnSender = auto()
    U8 = auto()
    U64 = auto()
    U128 = auto()
    Vector = auto()
    Unrestricted = auto()
    While = auto()
    LBrace = auto()
    Pipe = auto()
    PipePipe = auto()
    RBrace = auto()
    LSquare = auto()
    RSquare = auto()
    PeriodPeriod = auto()


    # Return True if the given token is the beginning of a specification directive for the Move
    # prover
    def is_spec_directive(self) -> bool:
        if self in [Tok.Ensures, Tok.Requires, Tok.SucceedsIf, Tok.AbortsIf]:
            return True
        else:
            return False


@dataclass
class Lexer:
    spec_mode: bool
    file: str
    text: str
    prev_end: usize
    cur_start: usize
    cur_end: usize
    token: Tok


    @classmethod
    def new(cls, file: str, s: str) -> Lexer:
        return Lexer(
            spec_mode= False, # read tokens without trailing punctuation during specs.
            file = file,
            text= s,
            prev_end= 0,
            cur_start= 0,
            cur_end= 0,
            token= Tok.EOF,
        )

    def peek(self) -> Tok:
        return self.token


    def content(self) -> str:
        return self.text[self.cur_start:self.cur_end]


    def file_name(self) -> str:
        return self.file


    def start_loc(self) -> usize:
        return self.cur_start


    def previous_end_loc(self) -> usize:
        return self.prev_end


    def lookahead(self) -> Tok:
        text = self.text[self.cur_end:].lstrip()
        offset = self.text.__len__() - text.__len__()
        (tok, _) = self.find_token(text, offset)
        return tok


    def advance(self) -> None:
        self.prev_end = self.cur_end
        text = self.text[self.cur_end:].lstrip()
        self.cur_start = self.text.__len__() - text.__len__()
        (token, lenn) = self.find_token(text, self.cur_start)
        self.cur_end = self.cur_start + lenn
        self.token = token


    def replace_token(
        self,
        token: Tok,
        lenn: usize,
    ) -> None:
        self.token = token
        self.cur_end = self.cur_start + lenn



    # Find the next token and its length without changing the state of the lexer.
    def find_token(
        self,
        text: str,
        start_offset: usize,
    ) -> Tuple[Tok, usize]:
        if not text:
            return (Tok.EOF, 0)

        ch = text[0]
        if ch >= '0' and ch <= '9':
            if (text.startswith("0x") or text.startswith("0X")) and text.__len__() > 2:
                hex_len = get_hex_digits_len(text[2:])
                if hex_len == 0:
                    # Fall back to treating this as a "0" token.
                    return (Tok.U64Value, 1)
                else:
                    return (Tok.AddressValue, 2 + hex_len)

            else:
                return get_decimal_number(text)

        elif (ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') or ch == '$' or ch == '_':
            lenn = get_name_len(text)
            name = text[:lenn]
            if not self.spec_mode:
                sss = text[lenn:]
                if not sss:
                    return (get_name_token(name), lenn)

                if sss[0] == '"':
                    # Special case for ByteArrayValue: h\"[0-9A-Fa-f]*\"
                    bvlen = 0
                    if name == "h":
                        bvlen = get_byte_array_value_len(text[(lenn + 1):])
                        if bvlen > 0:
                            return (Tok.ByteArrayValue, 2 + bvlen)

                    return (get_name_token(name), lenn)

                elif sss[0] == '.':
                    len2 = get_name_len(text[(lenn + 1):])
                    if len2 > 0:
                        return (Tok.DotNameValue, lenn + 1 + len2)
                    else:
                        return (get_name_token(name), lenn)

                elif sss[0] == '<':
                    lt_map = {
                        "vector" : (Tok.Vector, lenn), #TTODO: why not lenn + 1
                        "borrow_global" : (Tok.BorrowGlobal, lenn + 1),
                        "borrow_global_mut" : (Tok.BorrowGlobalMut, lenn + 1),
                        "exists" : (Tok.Exists, lenn + 1),
                        "move_from" : (Tok.MoveFrom, lenn + 1),
                        "move_to_sender" : (Tok.MoveToSender, lenn + 1),
                    }
                    if name in lt_map:
                        return lt_map[name]
                    else:
                        return (Tok.NameBeginTyValue, lenn + 1)

                elif sss[0] == '(':
                    lt_map = {
                        "assert" : (Tok.Assert, lenn + 1),
                        "copy" : (Tok.Copy, lenn + 1),
                        "move" : (Tok.Move, lenn + 1),
                    }
                    if name in lt_map:
                        return lt_map[name]
                    else:
                        return (get_name_token(name), lenn)

                elif sss[0] == ':':
                    lt_map = {
                        "modules" : (Tok.Modules, lenn + 1),
                        "script" : (Tok.Script, lenn + 1),
                    }
                    if name in lt_map:
                        return lt_map[name]
                    else:
                        return (get_name_token(name), lenn)
                else:
                    return (get_name_token(name), lenn)
            else:
                return (get_name_token(name), lenn) # just return the name in spec_mode

        elif ch == '&':
            if text.startswith("&mut "):
                return (Tok.AmpMut, 5)
            elif text.startswith("&&"):
                return (Tok.AmpAmp, 2)
            else:
                return (Tok.Amp, 1)

        elif ch == '|':
            if text.startswith("||"):
                return (Tok.PipePipe, 2)
            else:
                return (Tok.Pipe, 1)

        elif ch == '=':
            if text.startswith("==>"):
                return (Tok.EqualEqualGreater, 3)
            elif text.startswith("=="):
                return (Tok.EqualEqual, 2)
            else:
                return (Tok.Equal, 1)

        elif ch == '!':
            if text.startswith("!="):
                return (Tok.ExclaimEqual, 2)
            else:
                return (Tok.Exclaim, 1)

        elif ch == '<':
            if text.startswith("<="):
                return (Tok.LessEqual, 2)
            elif text.startswith("<<"):
                return (Tok.LessLess, 2)
            else:
                return (Tok.Less, 1)

        elif ch == '>':
            if text.startswith(">="):
                return (Tok.GreaterEqual, 2)
            elif text.startswith(">>"):
                return (Tok.GreaterGreater, 2)
            else:
                return (Tok.Greater, 1)

        elif ch == '%':
            return (Tok.Percent, 1)
        elif ch == '(':
            return (Tok.LParen, 1)
        elif ch == ')':
            return (Tok.RParen, 1)
        elif ch == '*':
            return (Tok.Star, 1)
        elif ch == '+':
            return (Tok.Plus, 1)
        elif ch == ',':
            return (Tok.Comma, 1)
        elif ch == '-':
            return (Tok.Minus, 1)
        elif ch == '.':
            if text.startswith(".."):
                return (Tok.PeriodPeriod, 2) # range, for specs
            else:
                return (Tok.Period, 1)

        elif ch == '/':
            return (Tok.Slash, 1)
        elif ch == ':':
            if text.startswith(":="):
                return (Tok.ColonEqual, 2) # spec update
            else:
                return (Tok.Colon, 1)

        elif ch == ';':
            return (Tok.Semicolon, 1)
        elif ch == '^':
            return (Tok.Caret, 1)
        elif ch == '{':
            return (Tok.LBrace, 1)
        elif ch == '}':
            return (Tok.RBrace, 1)
        elif ch == '[':
            return (Tok.LSquare, 1)
        elif ch == ']':
            return (Tok.RSquare, 1)
        else:
            idx = ByteIndex(start_offset)
            location = Loc(self.file_name(), Span.new(idx, idx))
            raise ParseErrorInvalidToken(location)


# Return the length of the substring matching [a-zA-Z$_][a-zA-Z0-9$_]
def get_name_len(text: str) -> usize:
    # If the first character is 0..=9 or EOF, then return a length of 0.
    if not text:
        return 0
    if text[0] >= '0' and text[0] <= '9':
        return 0
    for i, ch in enumerate(text):
        od = ord(ch)
        if od >= ord('a') and od <= ord('z'):
            continue
        if od >= ord('A') and od <= ord('Z'):
            continue
        if od >= ord('0') and od <= ord('9'):
            continue
        if ch == '_':
            continue
        return i
    return len(text)


def _get_digits_len(text: str) -> usize:
    for i, ch in enumerate(text):
        od = ord(ch)
        if od >= ord('0') and od <= ord('9'):
            continue
        return i
    return len(text)


def get_decimal_number(text: str) -> Tuple[Tok, usize]:
    lenn = _get_digits_len(text)
    rest = text[lenn:]
    if rest.startswith("u8"):
        return (Tok.U8Value, lenn + 2)
    elif rest.startswith("u64"):
        return (Tok.U64Value, lenn + 3)
    elif rest.startswith("u128"):
        return (Tok.U128Value, lenn + 4)
    else:
        return (Tok.U64Value, lenn)


# Return the length of the substring containing characters in [0-9a-fA-F].
def get_hex_digits_len(text: str) -> usize:
    for i, ch in enumerate(text):
        od = ord(ch)
        if od >= ord('a') and od <= ord('f'):
            continue
        if od >= ord('A') and od <= ord('F'):
            continue
        if od >= ord('0') and od <= ord('9'):
            continue
        return i
    return len(text)


# Check for an optional sequence of hex digits following by a double quote, and return
# the length of that string if found. This is used to lex ByteArrayValue tokens after
# seeing the 'h"' prefix.
def get_byte_array_value_len(text: str) -> usize:
    hex_len = get_hex_digits_len(text)
    if len(text) > hex_len and text[hex_len:][0] == '"':
        return hex_len + 1
    else:
        return 0


def get_name_token(name: str) -> Tok:
    name_dict = {
        "_" : Tok.Underscore,
        "abort" : Tok.Abort,
        "aborts_if" : Tok.AbortsIf,
        "acquires" : Tok.Acquires,
        "address" : Tok.Address,
        "as" : Tok.As,
        "bool" : Tok.Bool,
        "break" : Tok.Break,
        "continue" : Tok.Continue,
        "else" : Tok.Else,
        "ensures" : Tok.Ensures,
        "false" : Tok.FALSE,
        "freeze" : Tok.Freeze,
        "get_txn_sender" : Tok.GetTxnSender,
        "global" : Tok.Global,              # spec language
        "global_exists" : Tok.GlobalExists, # spec language
        "to_u8" : Tok.ToU8,
        "to_u64" : Tok.ToU64,
        "to_u128" : Tok.ToU128,
        "if" : Tok.If,
        "import" : Tok.Import,
        "let" : Tok.Let,
        "loop" : Tok.Loop,
        "main" : Tok.Main,
        "module" : Tok.Module,
        "native" : Tok.Native,
        "invariant" : Tok.Invariant,
        "old" : Tok.Old,
        "public" : Tok.Public,
        "requires" : Tok.Requires,
        "resource" : Tok.Resource,
        "RET" : Tok.SpecReturn,
        "return" : Tok.Return,
        "struct" : Tok.Struct,
        "succeeds_if" : Tok.SucceedsIf,
        "synthetic" : Tok.Synthetic,
        "true" : Tok.TRUE,
        "txn_sender" : Tok.TxnSender,
        "u8" : Tok.U8,
        "u64" : Tok.U64,
        "u128" : Tok.U128,
        "unrestricted" : Tok.Unrestricted,
        "while" : Tok.While,
    }
    if name in name_dict:
        return name_dict[name]
    else:
        return Tok.NameValue
