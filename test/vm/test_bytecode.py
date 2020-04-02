from vm.file_format_common import *
from vm.file_format import *
from libra.rustlib import *
import pytest


def test_bytecode_default():
    assert Opcodes.RET == Bytecode.default(Opcodes.RET).tag
    code = Bytecode.default(Opcodes.MOVE_TO)
    assert code.tag == Opcodes.MOVE_TO
    assert code.value == (StructDefinitionIndex(0), NO_TYPE_ACTUALS)
