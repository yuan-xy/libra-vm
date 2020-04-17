from __future__ import annotations
from libra.transaction import TransactionOutput
from libra.vm_error import VMStatus
from enum import IntEnum
from dataclasses import dataclass
from typing import Union

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

    @classmethod
    def Other(cls, msg:str):
        return cls(ErrorKindTag.Other, msg)


    @classmethod
    def VMExecutionFailure(cls, v):
        return cls(ErrorKindTag.VMExecutionFailure, v)

    @classmethod
    def DiscardedTransaction(cls, v):
        return cls(ErrorKindTag.DiscardedTransaction, v)

    @classmethod
    def CheckerFailure(cls, v):
        return cls(ErrorKindTag.CheckerFailure, v)

    @classmethod
    def VerificationError(cls, v):
        return cls(ErrorKindTag.VerificationError, v)



