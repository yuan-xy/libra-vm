import abc
from libra_vm.lib import IndexKind
from libra.rustlib import usize

# Types meant for use by other parts of this crate, and by other crates that are designed to
# work with the internals of these data structures.


# Represents a module index.
class ModuleIndex(abc.ABC):
    KIND: IndexKind

    @abc.abstractmethod
    def into_index(self) -> usize:
        pass

