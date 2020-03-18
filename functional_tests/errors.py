from __future__ import annotations
from libra.transaction import TransactionOutput
from libra.vm_error import VMStatus
from enum import IntEnum
from dataclasses import dataclass

class ErrorKindTag(IntEnum):
    #[error("an error occurred when executing the transaction")]
    VMExecutionFailure = 1
    #[error("the transaction was discarded")]
    DiscardedTransaction = 2
    #[error("the checker has failed to match the directives against the output")]
    CheckerFailure = 3
    #[error("VerificationError({0:?})")]
    VerificationError = 4
    #[error("other error: {0}")]
    Other = 5


# Defines all errors in this crate.
@dataclass
class ErrorKind(Exception):
    tag: ErrorKindTag
    value: Union[TransactionOutput, VMStatus, str]


