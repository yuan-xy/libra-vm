from libra.vm_error import StatusCode, VMStatus
from typing import List
from dataclasses import dataclass, field

@dataclass
class VMException(Exception):
    vm_status: List[VMStatus] = field(default_factory=list)
