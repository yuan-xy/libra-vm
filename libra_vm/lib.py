import abc
from libra_storage.state_view import StateView
from libra.transaction import SignedTransaction, Transaction, TransactionOutput
from libra.vm_error import VMStatus
from typing import List, Optional, Any

# # The VM runtime
#
# ## Transaction flow
#
# This is the path taken to process a single transaction.
#
# ```text
#                   SignedTransaction
#                            +
#                            |
# +--------------------------|-------------------+
# | Validate  +--------------+--------------+    |
# |           |                             |    |
# |           |       check signature       |    |
# |           |                             |    |
# |           +--------------+--------------+    |
# |                          |                   |
# |                          |                   |
# |                          v                   |
# |           +--------------+--------------+    |
# |           |                             |    |
# |           |      check size and gas     |    |
# |           |                             |    +---------------------------------+
# |           +--------------+--------------+    |         validation error        |
# |                          |                   |                                 |
# |                          |                   |                                 |
# |                          v                   |                                 |
# |           +--------------+--------------+    |                                 |
# |           |                             |    |                                 |
# |           |         run prologue        |    |                                 |
# |           |                             |    |                                 |
# |           +--------------+--------------+    |                                 |
# |                          |                   |                                 |
# +--------------------------|-------------------+                                 |
#                            |                                                     |
# +--------------------------|-------------------+                                 |
# |                          v                   |                                 |
# |  Verify   +--------------+--------------+    |                                 |
# |           |                             |    |                                 |
# |           |     deserialize script,     |    |                                 |
# |           |     verify arguments        |    |                                 |
# |           |                             |    |                                 |
# |           +--------------+--------------+    |                                 |
# |                          |                   |                                 |
# |                          |                   |                                 v
# |                          v                   |                    +----------------+------+
# |           +--------------+--------------+    |                    |                       |
# |           |                             |    +------------------->+ discard, no write set |
# |           |     deserialize modules     |    | verification error |                       |
# |           |                             |    |                    +----------------+------+
# |           +--------------+--------------+    |                                 ^
# |                          |                   |                                 |
# |                          |                   |                                 |
# |                          v                   |                                 |
# |           +--------------+--------------+    |                                 |
# |           |                             |    |                                 |
# |           | verify scripts and modules  |    |                                 |
# |           |                             |    |                                 |
# |           +--------------+--------------+    |                                 |
# |                          |                   |                                 |
# +--------------------------|-------------------+                                 |
#                            |                                                     |
# +--------------------------|-------------------+                                 |
# |                          v                   |                                 |
# | Execute   +--------------+--------------+    |                                 |
# |           |                             |    |                                 |
# |           |        execute main         |    |                                 |
# |           |                             |    |                                 |
# |           +--------------+--------------+    |                                 |
# |                          |                   |                                 |
# |      success or failure  |                   |                                 |
# |                          v                   |                                 |
# |           +--------------+--------------+    |                                 |
# |           |                             |    +---------------------------------+
# |           |        run epilogue         |    | invariant violation (internal panic)
# |           |                             |    |
# |           +--------------+--------------+    |
# |                          |                   |
# |                          |                   |
# |                          v                   |
# |           +--------------+--------------+    |                    +-----------------------+
# |           |                             |    | execution failure  |                       |
# |           |       make write set        +------------------------>+ keep, only charge gas |
# |           |                             |    |                    |                       |
# |           +--------------+--------------+    |                    +-----------------------+
# |                          |                   |
# +--------------------------|-------------------+
#                            |
#                            v
#             +--------------+--------------+
#             |                             |
#             |  keep, transaction executed |
#             |        + gas charged        |
#             |                             |
#             +-----------------------------+
# ```




# This trait describes the VM's verification interfaces.
class VMVerifier(abc.ABC):
    # Executes the prologue of the Libra Account and verifies that the transaction is valid.
    # only. Returns `None` if the transaction was validated, or Some(VMStatus) if the transaction
    # was unable to be validated with status `VMStatus`.
    @abc.abstractmethod
    def validate_transaction(
        self,
        transaction: SignedTransaction,
        state_view: StateView,
    ) -> Optional[VMStatus]:
        pass


# This trait describes the VM's execution interface.
class VMExecutor(abc.ABC):
    # NOTE: At the moment there are no persistent caches that live past the end of a block (that's
    # why execute_block doesn't take self.)
    # There are some cache invalidation issues around transactions publishing code that need to be
    # sorted out before that's possible.

    # Executes a block of transactions and returns output for each one of them.
    @classmethod
    @abc.abstractmethod
    def execute_block(cls,
        transactions: List[Transaction],
        config: Any,
        state_view: StateView,
    ) -> List[TransactionOutput]:
        pass

