import abc
from libra.access_path import AccessPath
from canoser import Uint8
from typing import List, Optional


# `StateView` is a trait that defines a read-only snapshot of the global state. It is passed to
# the VM for transaction execution, during which the VM is guaranteed to read anything at the
# given state.
class StateView(abc.ABC):

    # Gets the state for a single access path.
    @abc.abstractmethod
    def get(self, access_path: AccessPath) -> Optional[bytes]:
        pass

    # Gets states for a list of access paths.
    @abc.abstractmethod
    def multi_get(self, access_paths: List[AccessPath]) -> List[Optional[bytes]]:
        pass

    # VM needs this method to know whether the current state view is for genesis state creation.
    # Currently TransactionPayload.WriteSet is only valid for genesis state creation.
    @abc.abstractmethod
    def is_genesis(self) -> bool:
        pass


# An empty `StateView`
class EmptyStateView(StateView):

    def get(self, _access_path: AccessPath) -> Optional[bytes]:
        return None

    def multi_get(self, _access_paths: List[AccessPath]) -> List[Optional[bytes]]:
        bail("unimplemented")

    def is_genesis(self) -> bool:
        return True


