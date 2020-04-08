from __future__ import annotations
from compiler.ir_to_bytecode.syntax import *
from libra.account_address import Address
from move_ir.types.codespan import ByteIndex, Span
from move_ir.types import ast
from move_ir.types.location import *
# from codespan.Files
# from codespan_reporting.{
#     diagnostic.{Diagnostic, BlockLabel},
#     term.{
#         emit,
#         termcolor.{ColorChoice, StandardStream},
#         Config,
#     },
# }
from typing import List, Optional, Tuple
from dataclasses import dataclass
from libra.rustlib import bail, ensure, usize
from io import StringIO

char = str

# Determine if a character is an allowed eye-visible (printable) character.
#
# The only allowed printable characters are the printable ascii characters (SPACE through ~) and
# tabs. All other characters are invalid and we return False.
def is_permitted_printable_char(c: char) -> bool:
    x = ord(c)
    is_above_space = x >= 0x20 # Don't allow meta characters
    is_below_tilde = x <= 0x7E # Don't allow DEL meta character
    is_tab = x == 0x09 # Allow tabs
    return (is_above_space and is_below_tilde) or is_tab


# Determine if a character is a permitted newline character.
#
# The only permitted newline character is \n. All others are invalid.
def is_permitted_newline_char(c: char) -> bool:
    x = ord(c)
    return x == 0x0A


# Determine if a character is permitted character.
#
# A permitted character is either a permitted printable character, or a permitted
# newline. Any other characters are disallowed from appearing in the file.
def is_permitted_char(c: char) -> bool:
    return is_permitted_printable_char(c) or is_permitted_newline_char(c)


def verify_string(string: str) -> None:
    for x in string:
        if not is_permitted_char(x):
            bail(
                "Parser Error: invalid character {} found when reading file.\
                 Only ascii printable, tabs (\\t), and \\n line ending characters are permitted.",
                x
            )


def strip_comments(source: str) -> str:
    SLASH: char = '/'
    SPACE: char = ' '

    in_comment = False
    acc = StringIO()
    length = len(source)

    def next_char_slash(i):
        ni = i + 1
        if ni >= length:
            return False
        return source[ni] == SLASH

    for i, ch in enumerate(source):
        at_newline = is_permitted_newline_char(ch)
        at_or_after_slash_slash = in_comment or (ch == SLASH and next_char_slash(i))
        in_comment = not at_newline and at_or_after_slash_slash
        if in_comment:
            acc.write(SPACE)
        else:
            acc.write(ch)

    return acc.getvalue()


# We restrict strings to only ascii visual characters (0x20 <= c <= 0x7E) or a permitted newline
# character--\n--or a tab--\t.
def strip_comments_and_verify(string: str) -> str:
    verify_string(string)
    return strip_comments(string)


# Given the raw input of a file, creates a `ScriptOrModule` enum
# Fails with `Err(_)` if the text cannot be parsed`
def parse_script_or_module(file_name: str, s: str) -> ast.ScriptOrModule:
    stripped_string = strip_comments_and_verify(s)
    try:
        return syntax.parse_script_or_module_string(file_name, stripped_string)
    except ParseError as e:
        handle_error(e, s) #TTODO: why not stripped_string instead of s


# Given the raw input of a file, creates a `Script` struct
# Fails with `Err(_)` if the text cannot be parsed
def parse_script(file_name: str, script_str: str) -> ast.Script:
    stripped_string = strip_comments_and_verify(script_str)
    try:
        return syntax.parse_script_string(file_name, stripped_string)
    except ParseError as e:
        handle_error(e, stripped_string)




# Given the raw input of a file, creates a single `ModuleDefinition` struct
# Fails with `Err(_)` if the text cannot be parsed
def parse_module(file_name: str, modules_str: str) -> ast.ModuleDefinition:
    stripped_string = strip_comments_and_verify(modules_str)
    try:
        return syntax.parse_module_string(file_name, stripped_string)
    except ParseError as e:
        handle_error(e, stripped_string)


# Given the raw input of a file, creates a single `Cmd_` struct
# Fails with `Err(_)` if the text cannot be parsed
def parse_cmd_(
    file_name: str,
    cmd_str: str,
    _sender_address: Address,
) -> ast.Cmd_:
    stripped_string = strip_comments_and_verify(cmd_str)
    try:
        return syntax.parse_cmd_string(file_name, stripped_string)
    except ParseError as e:
        handle_error(e, stripped_string)


def handle_error(e: ParseError, code_str: str) -> None:
    if isinstance(e, ParseErrorInvalidToken):
        # files = Files.new()
        # id = files.add(location.file(), code_str)
        # lbl = BlockLabel.new(id, location.span(), "Invalid Token")
        # error = Diagnostic.new_error("Parser Error", lbl)
        # writer = StandardStream.stderr(ColorChoice.Auto)
        # emit(writer, &Config.default(), &files, &error)
        print(e)
        msg = e.__str__()
    elif isinstance(e, ParseErrorUser):
        print(e)
        msg = e.error
    else:
        bail("unreachable!")
    bail("ParserError: {}", msg)

