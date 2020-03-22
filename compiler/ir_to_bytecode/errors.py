from __future__ import annotations
from libra.vm_error import VMStatus
from typing import List, Any
from dataclasses import dataclass, field


class InternalCompilerError(Exception):
    pass


@dataclass
class BoundsCheckErrors(InternalCompilerError):
    v0: List[VMStatus]

    def __str__(self):
        return f"BoundsCheckErrors:Post-compile bounds check errors: {self.v0}"


