from libra.vm_error import StatusCode, VMStatus
from typing import List, Union
from dataclasses import dataclass, field

@dataclass
class VMException(Exception):
    vm_status: List[VMStatus]

    def __init__(self, status: Union[VMStatus, List[VMStatus]]):
        if isinstance(status, VMStatus):
            self.vm_status = [status]
        else:
            self.vm_status = status
