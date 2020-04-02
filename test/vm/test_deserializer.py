from vm.file_format import CompiledModule, CompiledScript
from vm.file_format_common import *
from libra.vm_error import StatusCode, VMStatus
from vm.vm_exception import VMException
import pytest

def test_malformed_1():
    # empty binary
    binary = []
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.MALFORMED


def test_malformed_2():
    # under-sized binary
    binary = [0, 0, 0]
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.MALFORMED


def test_malformed_3():
    # bad magic
    binary = [0] * 15
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.BAD_MAGIC


def test_malformed_4():
    # only magic
    binary = BinaryConstants.LIBRA_MAGIC
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.MALFORMED


def test_malformed_5():
    # bad major version
    binary = bytearray(BinaryConstants.LIBRA_MAGIC)
    binary.append(2); # major version
    binary.append(0); # minor version
    binary.append(10); # table count
    binary.append(0); # rest of binary ;)
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.UNKNOWN_VERSION

def test_malformed_6():
    # bad minor version
    binary = bytearray(BinaryConstants.LIBRA_MAGIC)
    binary.append(1); # major version
    binary.append(1); # minor version
    binary.append(10); # table count
    binary.append(0); # rest of binary ;)
    with pytest.raises(VMException) as excinfo:
        CompiledScript.deserialize(binary)
    vm_error = excinfo.value.vm_status[0]
    assert vm_error.major_status == StatusCode.UNKNOWN_VERSION

