from libra.transaction import TransactionStatus
from libra.vm_error import StatusCode, StatusType, VMStatus
from libra.rustlib import usize
from typing import List, Optional, Mapping


# constants used to create counters
TXN_EXECUTION_KEEP = "txn.execution.keep"
TXN_EXECUTION_DISCARD = "txn.execution.discard"
TXN_VERIFICATION_SUCCESS = "txn.verification.success"
TXN_VERIFICATION_FAIL = "txn.verification.fail"
TXN_BLOCK_COUNT = "txn.block.count"

TXN_TOTAL_TIME_TAKEN = "txn_gas_total_time_taken"
TXN_VERIFICATION_TIME_TAKEN = "txn_gas_verification_time_taken"
TXN_VALIDATION_TIME_TAKEN = "txn_gas_validation_time_taken"
TXN_EXECUTION_TIME_TAKEN = "txn_gas_execution_time_taken"
TXN_PROLOGUE_TIME_TAKEN = "txn_gas_prologue_time_taken"
TXN_EPILOGUE_TIME_TAKEN = "txn_gas_epilogue_time_taken"
TXN_EXECUTION_GAS_USAGE = "txn_gas_execution_gas_usage"
TXN_TOTAL_GAS_USAGE = "txn_gas_total_gas_usage"


# # the main metric (move_vm)
# pub static VM_COUNTERS: Lazy<OpMetrics> = Lazy.new(|| OpMetrics.new_and_registered("move_vm"))

# static VERIFIED_TRANSACTION: Lazy<IntCounter> =
#     Lazy.new(|| VM_COUNTERS.counter(TXN_VERIFICATION_SUCCESS))
# static BLOCK_TRANSACTION_COUNT: Lazy<IntGauge> = Lazy.new(|| VM_COUNTERS.gauge(TXN_BLOCK_COUNT))

# # Wrapper around time.Instant.
# def start_profile() -> Instant {
#     Instant.now()
# }

# Reports the number of transactions in a block.
def report_block_count(count: usize):
    pass
    # match i64.try_from(count) {
    #     val => BLOCK_TRANSACTION_COUNT.set(val),
    #     Err(_) => BLOCK_TRANSACTION_COUNT.set(std.i64.MAX),
    # }


# # All statistics gather operations for the time taken/gas usage should go through this macro. This
# # gives us the ability to turn these metrics on and off easily from one place.
# #[macro_export]
# macro_rules! record_stats {
#     # Gather some information that is only needed in relation to recording statistics
#     (info | $($stmt:stmt);+;) => {
#         $($stmt);+
#     }
#     # Set the $ident gauge to $amount
#     (gauge set | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.set($ident, $amount as f64)
#     }
#     # Increment the $ident gauge by $amount
#     (gauge inc | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.add($ident, $amount as f64)
#     }
#     # Decrement the $ident gauge by $amount
#     (gauge dec | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.sub($ident, $amount as f64)
#     }
#     # Set the $ident gauge to $amount
#     (counter set | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.set($ident, $amount as f64)
#     }
#     # Increment the $ident gauge by $amount
#     (counter inc | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.add($ident, $amount as f64)
#     }
#     # Decrement the $ident gauge by $amount
#     (counter dec | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.sub($ident, $amount as f64)
#     }
#     # Set the gas histogram for $ident to be $amount.
#     (observe | $ident:ident | $amount:expr) => {
#         VM_COUNTERS.observe($ident, $amount as f64)
#     }
#     # Per-block info: time and record the amount of time it took to execute $block under the
#     # $ident histogram. NB that this does not provide per-transaction level information, but will
#     # only per-block information.
#     (time_hist | $ident:ident | $block:block) => {{
#         timer = start_profile()
#         tmp = $block
#         duration = timer.elapsed()
#         VM_COUNTERS.observe_duration($ident, duration)
#         tmp
#     }}
# }

# Reports the result of a transaction execution.
#
# Counters are prefixed with `TXN_EXECUTION_KEEP` or `TXN_EXECUTION_DISCARD`.
# The prefix can be used with regex to combine different counters in a dashboard.
def report_execution_status(status: TransactionStatus):
    pass
    # match status {
    #     TransactionStatus.Keep(vm_status) => inc_counter(TXN_EXECUTION_KEEP, vm_status),
    #     TransactionStatus.Discard(vm_status) => inc_counter(TXN_EXECUTION_DISCARD, vm_status),
    # }


# Reports the result of a transaction verification.
#
# Counters are prefixed with `TXN_VERIFICATION_SUCCESS` or `TXN_VERIFICATION_FAIL`.
# The prefix can be used with regex to combine different counters in a dashboard.
def report_verification_status(result: Optional[VMStatus]):
    pass
    # match result {
    #     None => VERIFIED_TRANSACTION.inc(),
    #     Some(status) => inc_counter(TXN_VERIFICATION_FAIL, status),
    # }


# Increments one of the counter for verification or execution.
def inc_counter(prefix: str, status: VMStatus):
    pass
#     match status.status_type() {
#         StatusType.Deserialization => {
#             # all serialization error are lumped into one bucket
#             VM_COUNTERS.inc(&format!("{}.deserialization", prefix))
#         }
#         StatusType.Execution => {
#             # counters for ExecutionStatus are as granular as the enum
#             VM_COUNTERS.inc(&format!("{}.{}", prefix, status))
#         }
#         StatusType.InvariantViolation => {
#             # counters for VMInvariantViolationError are as granular as the enum
#             VM_COUNTERS.inc(&format!("{}.invariant_violation.{}", prefix, status))
#         }
#         StatusType.Validation => {
#             # counters for validation errors are grouped according to get_validation_status()
#             VM_COUNTERS.inc(&format!(
#                 "{}.validation.{}",
#                 prefix,
#                 get_validation_status(status.major_status)
#             ))
#         }
#         StatusType.Verification => {
#             # all verifier errors are lumped into one bucket
#             VM_COUNTERS.inc(&format!("{}.verifier_error", prefix))
#         }
#         StatusType.Unknown => {
#             VM_COUNTERS.inc(&format!("{}.Unknown", prefix))
#         }
#     }
# }

# Translate a `VMValidationStatus` enum to a set of strings that are appended to a 'base' counter
# name.
def get_validation_status(validation_status: StatusCode) ->  str:
    return StatusCode.get_name(validation_status)
