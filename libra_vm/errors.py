from libra_vm import IndexKind
from libra import Address
from libra.transaction import TransactionStatus
from libra.vm_error import StatusCode, VMStatus

from libra.rustlib import ensure, bail, usize
from canoser import Uint8, Uint32, Uint16, Uint64, Uint128
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

def format_str(astr, *args):
    return astr.format(*args)

# We may want to eventually move this into the VM runtime since it is a semantic decision that
# need to be made by the VM. But for now, this will reside here.
def vm_result_to_transaction_status(result: VMStatus) -> TransactionStatus:
    # The decision as to whether or not a transaction should be dropped should be able to be
    # determined solely by the VMStatus. This then means that we can audit/verify any decisions
    # made by the VM externally on whether or not to discard or keep the transaction output by
    # inspecting the contained VMStatus.
    #vm_status = vm_status_of_result(result)
    #vm_status.into()
    return TransactionStatus.from_vm_status(result)


# TODO: Fill in the details for Locations. Ideally it should be a unique handle into a function and
# a pc.
class Location:
    pass

# Error codes that can be emitted by the prologue. These have special significance to the VM when
# they are raised during the prologue. However, they can also be raised by user code during
# execution of a transaction script. They have no significance to the VM in that case.
EBAD_SIGNATURE: Uint64 = 1 # signature on transaction is invalid
EBAD_ACCOUNT_AUTHENTICATION_KEY: Uint64 = 2 # auth key in transaction is invalid
ESEQUENCE_NUMBER_TOO_OLD: Uint64 = 3 # transaction sequence number is too old
ESEQUENCE_NUMBER_TOO_NEW: Uint64 = 4 # transaction sequence number is too new
EACCOUNT_DOES_NOT_EXIST: Uint64 = 5 # transaction sender's account does not exist
ECANT_PAY_GAS_DEPOSIT: Uint64 = 6 # insufficient balance to pay for gas deposit
ETRANSACTION_EXPIRED: Uint64 = 7 # transaction expiration time exceeds block time.

# Generic error codes. These codes don't have any special meaning for the VM, but they are useful
# conventions for debugging
EINSUFFICIENT_BALANCE: Uint64 = 10 # withdrawing more than an account contains
EINSUFFICIENT_PRIVILEGES: Uint64 = 11 # user lacks the credentials to do something

EASSERT_ERROR: Uint64 = 42 # catch-all error code for assert failures

# pub type VMResult<T> = ::std::result::Result<T, VMStatus>;
# pub type BinaryLoaderResult<T> = ::std::result::Result<T, VMStatus>;


#########################/
# Conversion functions from internal VM statuses into external VM statuses
#########################/

def vm_status_of_result(result: VMStatus) -> VMStatus:
    bail("not implemented!")

# FUTURE: At the moment we can't pass transaction metadata or the signed transaction due to
# restrictions in the two places that this function is called. We therefore just pass through what
# we need at the moment---the sender address---but we may want/need to pass more data later on.
def convert_prologue_runtime_error(err: VMStatus, txn_sender: Address) -> VMStatus:
    if err.major_status == StatusCode.ABORTED:
        def acc_not_exsit():
            error_msg = format_str("sender address: {}", txn_sender)
            status = VMStatus(StatusCode.SENDING_ACCOUNT_DOES_NOT_EXIST)
            status.message = error_msg
            return status

        adict = {
            # Invalid authentication key
            EBAD_ACCOUNT_AUTHENTICATION_KEY : VMStatus(StatusCode.INVALID_AUTH_KEY),
            # Sequence number too old
            ESEQUENCE_NUMBER_TOO_OLD : VMStatus(StatusCode.SEQUENCE_NUMBER_TOO_OLD),
            # Sequence number too new
            ESEQUENCE_NUMBER_TOO_NEW : VMStatus(StatusCode.SEQUENCE_NUMBER_TOO_NEW),
            # Sequence number too new
            EACCOUNT_DOES_NOT_EXIST : acc_not_exsit(),
            # Can't pay for transaction gas deposit/fee
            ECANT_PAY_GAS_DEPOSIT : VMStatus(StatusCode.INSUFFICIENT_BALANCE_FOR_TRANSACTION_FEE),
            ETRANSACTION_EXPIRED : VMStatus(StatusCode.TRANSACTION_EXPIRED),
        }
        if err.sub_status in adict:
            return adict[err.sub_status]
    return deepcopy(err)


def vm_error(location: Location, err: StatusCode) -> VMStatus:
    msg = format_str("At location {}", location)
    return VMStatus(err).with_message(msg)


def bytecode_offset_err(
    kind: IndexKind,
    offset: usize,
    lens: usize,
    bytecode_offset: usize,
    status: StatusCode,
) -> VMStatus:
    msg = format_str(
        "Index {} out of bounds for {} at bytecode offset {} while indexing {}",
        offset, lens, bytecode_offset, kind
    )
    return VMStatus(status).with_message(msg)


def bounds_error(kind: IndexKind, idx: usize, len: usize, err: StatusCode) -> VMStatus:
    msg = format_str(
        "Index {} out of bounds for {} while indexing {}",
        idx, len, kind
    )
    return VMStatus(err).with_message(msg)


def verification_error(kind: IndexKind, idx: usize, err: StatusCode) -> VMStatus:
    msg = format_str("at index {} while indexing {}", idx, kind)
    return VMStatus(err).with_message(msg)


def append_err_info(status: VMStatus, kind: IndexKind, idx: usize) -> VMStatus:
    msg = format_str("at index {} while indexing {}", idx, kind)
    return status.append_message_with_separator(' ', msg)


def err_at_offset(status: StatusCode, offset: usize) -> VMStatus:
    msg = format_str("At offset {}", offset)
    return VMStatus(status).with_message(msg)

