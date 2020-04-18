from mol.compiler.ir_to_bytecode.parser import *
import pytest

def test_verify_character_whitelist():
    good_chars = [x for x in range(0x20, 0x7E+1)]
    good_chars.append(0x0A)
    good_chars.append(0x09)

    bad_chars = [x for x in range(0x0, 0x09)]
    bad_chars.extend([x for x in range(0x0B, 0x1F+1)])
    bad_chars.append(0x7F)

    # Test to make sure that all the characters that are in the whitelist pass.
    s = bytes(good_chars).decode("utf-8")
    verify_string(s)


    # Test to make sure that we fail for all characters not in the whitelist.
    for bad_char in bad_chars:
        good_chars.append(bad_char)
        s = bytes(good_chars[-3:]).decode("utf-8")
        with pytest.raises(AssertionError) as excinfo:
            verify_string(s)
        good_chars.pop()



def test_strip_comments():
    good_chars = [x for x in range(0x20, 0x7E+1)]
    good_chars.append(0x09)
    good_chars.append(0x0A)
    good_chars.insert(0, 0x2F)
    good_chars.insert(0, 0x2F)

    s = bytes(good_chars).decode("utf-8")
    s = strip_comments(s)
    for x in s:
        assert x == ' ' or x == '\t' or x == '\n'

    # Remove the \n at the end of the line
    good_chars.pop()

    bad_chars = [
        0x0B, # VT
        0x0C, # FF
        0x0D, # CR
        0x0D, 0x0A, # CRLF
        0xC2, 0x85, # NEL
        0xE2, 0x80, 0xA8, # LS
        0xE2, 0x80, 0xA9, # PS
        0x1E, # RS
        0x15, # NL
        0x76, # NEWLINE
    ]

    bad_chars = bytes(bad_chars).decode("utf-8")
    good_chars = bytes(good_chars).decode("utf-8")

    for bad_char in bad_chars:
        s = good_chars + bad_char + '\n' + 'a'
        x = strip_comments(s)
        for c in x:
            assert c == ' ' or c == '\t' or c == '\n' or c == 'a'

