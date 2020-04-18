from __future__ import annotations
from mol.move_vm.types.identifier import create_access_path, resource_storage_key
from mol.move_vm.types.chain_state import ChainState
from mol.move_vm.state.execution_context import SystemExecutionContext, TransactionExecutionContext
from mol.libra_vm.counters import *
from mol.move_vm.state.data_cache import BlockDataCache, RemoteCache, RemoteStorage
from mol.move_vm.runtime.move_vm import MoveVM
from mol.libra_vm.lib import VMVerifier, VMExecutor
from mol.libra_vm.system_module_names import *
from libra_storage.state_view import StateView
from mol.bytecode_verifier import VerifiedModule
from libra import Address
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.hasher import HashValue
from libra.block_metadata import BlockMetadata
from libra.transaction import (
    ChangeSet, SignatureCheckedTransaction, SignedTransaction, Transaction,
    TransactionArgument, TransactionOutput, TransactionPayload, TransactionStatus,
    MAX_TRANSACTION_SIZE_IN_BYTES
    )
from libra.vm_error import StatusCode, SubStatus, VMStatus
from libra.transaction import WriteSet
from mol.vm.vm_exception import VMException
from mol.vm.errors import convert_prologue_runtime_error, format_str
from mol.vm.gas_schedule import (
    AbstractMemorySize, CostTable, GasAlgebra, GasCarrier, GasUnits, GAS_SCHEDULE_NAME,
    MAXIMUM_NUMBER_OF_GAS_UNITS, MAX_PRICE_PER_GAS_UNIT, MIN_PRICE_PER_GAS_UNIT, calculate_intrinsic_gas
)
from mol.vm.transaction_metadata import TransactionMetadata
from mol.move_vm.types.values import Value
from dataclasses import dataclass
from typing import List, Optional, Mapping, Union
from libra.rustlib import usize
from canoser import RustEnum, Uint64, MapT, BytesT
import traceback
import logging

logger = logging.getLogger(__name__)


# A wrapper to make VMRuntime standalone and thread safe.
@dataclass
class LibraVM(VMVerifier, VMExecutor):
    move_vm: MoveVM
    gas_schedule: Optional[CostTable] = None

    @classmethod
    def new(cls) -> LibraVM:
        return cls(MoveVM.new(), None)


    # Provides access to some internal APIs of the Libra VM.
    def internals(self) -> LibraVMInternals:
        return LibraVMInternals(self)


    def load_configs(self, state: StateView):
        self.load_configs_impl(RemoteStorage.new(state))


    def load_configs_impl(self, data_cache: RemoteCache):
        self.gas_schedule = self.fetch_gas_schedule(data_cache)


    def fetch_gas_schedule(self, data_cache: RemoteCache) -> CostTable:
        try:
            address = AccountConfig.association_address_bytes()
            ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))
            gas_struct_tag = self.move_vm\
                .resolve_struct_tag_by_name(GAS_SCHEDULE_MODULE, GAS_SCHEDULE_NAME, ctx)
                # .map_err(|_| {
                #     VMStatus(StatusCode.GAS_SCHEDULE_ERROR)
                #         .with_sub_status(SubStatus.GSE_UNABLE_TO_LOAD_MODULE)
                # })

            access_path = create_access_path(address, gas_struct_tag)
            data_blob = data_cache.get(access_path)
            table = CostTable.deserialize(data_blob)
            return table
        except Exception as err:
            raise VMException(VMStatus(StatusCode.GAS_SCHEDULE_ERROR)\
                    .with_sub_status(SubStatus.GSE_UNABLE_TO_LOAD_RESOURCE).with_message(err.__str__()))


    def get_gas_schedule(self) -> CostTable:
        if self.gas_schedule:
            return self.gas_schedule
        else:
            raise VMException(VMStatus(StatusCode.VM_STARTUP_FAILURE)
                .with_sub_status(SubStatus.VSF_GAS_SCHEDULE_NOT_FOUND))


    def check_payload(
        self,
        payload: TransactionPayload,
        state_view: StateView,
    ) -> None:
        if payload.WriteSet:
            self.check_change_set(payload.value, state_view)
            # TODO: Remove WriteSet from TransactionPayload.
        elif payload.Script:
            pass
            # if !is_allowed_script(self.config.publishing_options, &script.code()) {
            #     logger.warning("[VM] Custom scripts not allowed: {}", &script.code())
            #     raise VMException(VMStatus(StatusCode.UNKNOWN_SCRIPT))
        elif payload.Module:
            pass
                # if !self.config.publishing_options.is_open() {
                #     logger.warning("[VM] Custom modules not allowed")
                #     raise VMException(VMStatus(StatusCode.UNKNOWN_MODULE))
        else:
            raise VMException(VMStatus(StatusCode.UNKNOWN_SCRIPT))



    def check_change_set(self, change_set: ChangeSet, state_view: StateView) -> None:
        # TODO: Replace this logic with actual checks.
        if state_view.is_genesis():
            for (_access_path, write_op) in change_set.write_set():
                # Genesis transactions only add entries, never delete them.
                if write_op.is_deletion():
                    logger.error("[VM] Bad genesis block")
                    # TODO: return more detailed error somehow
                    raise VMException(VMStatus(StatusCode.INVALID_WRITE_SET))

        else:
            raise VMException(VMStatus(StatusCode.REJECTED_WRITE_SET))


    def check_gas(self, txn: SignedTransaction) -> None:
        # Do not check gas limit for writeset transaction.
        if txn.payload.WriteSet:
            return

        raw_bytes_len = AbstractMemorySize.new(txn.raw_txn_bytes_len())
        # The transaction is too large.
        if txn.raw_txn_bytes_len() > MAX_TRANSACTION_SIZE_IN_BYTES:
            error_str = format_str(
                "max size: {}, txn size: {}",
                MAX_TRANSACTION_SIZE_IN_BYTES,
                raw_bytes_len.get()
            )
            logger.warning(
                "[VM] Transaction size too big {} (max {})",
                raw_bytes_len.get(),
                MAX_TRANSACTION_SIZE_IN_BYTES
            )
            raise VMException(
                VMStatus(StatusCode.EXCEEDED_MAX_TRANSACTION_SIZE).with_message(error_str)
            )


        # Check is performed on `txn.raw_txn_bytes_len()` which is the same as
        # `raw_bytes_len`
        assert (raw_bytes_len.get() <= MAX_TRANSACTION_SIZE_IN_BYTES)

        # The submitted max gas units that the transaction can consume is greater than the
        # maximum number of gas units bound that we have set for any
        # transaction.
        if txn.max_gas_amount > MAXIMUM_NUMBER_OF_GAS_UNITS.get():
            error_str = format_str(
                "max gas units: {}, gas units submitted: {}",
                MAXIMUM_NUMBER_OF_GAS_UNITS.get(),
                txn.max_gas_amount
            )
            logger.warning(
                "[VM] Gas unit error; max {}, submitted {}",
                MAXIMUM_NUMBER_OF_GAS_UNITS.get(),
                txn.max_gas_amount
            )
            raise VMException(
                VMStatus(StatusCode.MAX_GAS_UNITS_EXCEEDS_MAX_GAS_UNITS_BOUND)
                    .with_message(error_str),
            )


        # The submitted transactions max gas units needs to be at least enough to cover the
        # intrinsic cost of the transaction as calculated against the size of the
        # underlying `RawTransaction`
        min_txn_fee = calculate_intrinsic_gas(raw_bytes_len)
        if txn.max_gas_amount < min_txn_fee.get():
            error_str = format_str(
                "min gas required for txn: {}, gas submitted: {}",
                min_txn_fee.get(),
                txn.max_gas_amount
            )
            logger.warning(
                "[VM] Gas unit error; min {}, submitted {}",
                min_txn_fee.get(),
                txn.max_gas_amount
            )
            raise VMException(
                VMStatus(StatusCode.MAX_GAS_UNITS_BELOW_MIN_TRANSACTION_GAS_UNITS)
                    .with_message(error_str)
            )


        # The submitted gas price is less than the minimum gas unit price set by the VM.
        # NB: MIN_PRICE_PER_GAS_UNIT may equal zero, but need not in the future. Hence why
        # we turn off the clippy warning.
        #[allow(clippy.absurd_extreme_comparisons)]
        below_min_bound = txn.gas_unit_price < MIN_PRICE_PER_GAS_UNIT.get()
        if below_min_bound:
            error_str = format_str(
                "gas unit min price: {}, submitted price: {}",
                MIN_PRICE_PER_GAS_UNIT.get(),
                txn.gas_unit_price
            )
            logger.warning(
                "[VM] Gas unit error; min {}, submitted {}",
                MIN_PRICE_PER_GAS_UNIT.get(),
                txn.gas_unit_price
            )
            raise VMException(
                VMStatus(StatusCode.GAS_UNIT_PRICE_BELOW_MIN_BOUND).with_message(error_str)
            )


        # The submitted gas price is greater than the maximum gas unit price set by the VM.
        if txn.gas_unit_price > MAX_PRICE_PER_GAS_UNIT.get():
            error_str = format_str(
                "gas unit max price: {}, submitted price: {}",
                MAX_PRICE_PER_GAS_UNIT.get(),
                txn.gas_unit_price
            )
            logger.warning(
                "[VM] Gas unit error; min {}, submitted {}",
                MAX_PRICE_PER_GAS_UNIT.get(),
                txn.gas_unit_price
            )
            raise VMException(
                VMStatus(StatusCode.GAS_UNIT_PRICE_ABOVE_MAX_BOUND).with_message(error_str)
            )


    def verify_transaction_impl(
        self,
        transaction: SignatureCheckedTransaction,
        state_view: StateView,
        remote_cache: RemoteCache,
    ) -> VerifiedTranscationPayload:
        transaction = transaction.into_inner()
        ctx = SystemExecutionContext.new(remote_cache, GasUnits.new(0))
        self.check_gas(transaction)
        self.check_payload(transaction.payload, state_view)
        txn_data = TransactionMetadata.new(transaction)
        if transaction.payload.Script:
            script = transaction.payload.value
            self.run_prologue(ctx, txn_data)
            return VerifiedTranscationPayload('Script',(
                script.code,
                script.args,
            ))
        elif transaction.payload.Module:
            module = transaction.payload.value
            self.run_prologue(ctx, txn_data)
            return VerifiedTranscationPayload('Module', module.code)
        elif transaction.payload.WriteSet:
            raise VMException(VMStatus(StatusCode.UNREACHABLE))
        else:
            raise VMException(VMStatus(StatusCode.UNKNOWN_SCRIPT))



    def execute_verified_payload(
        self,
        remote_cache: BlockDataCache,
        txn_data: TransactionMetadata,
        payload: VerifiedTranscationPayload,
    ) -> TransactionOutput:
        ctx = TransactionExecutionContext.new(txn_data.max_gas_amount, remote_cache)
        # TODO: The logic for handling falied transaction fee is pretty ugly right now. Fix it later.
        failed_gas_left = GasUnits.new(0)
        try:
            if payload.Module:
                self.move_vm.publish_module(payload.value, ctx, txn_data)
                exec_flag = True
            elif payload.Script:
                (s, args) = payload.value
                try:
                    gas_schedule = self.get_gas_schedule()
                except VMException as err:
                    return discard_error_output(err.vm_status[0])
                self.move_vm.execute_script(
                    s,
                    gas_schedule,
                    ctx,
                    txn_data,
                    convert_txn_args(args),
                )
                # let gas_usage = txn_data.max_gas_amount().sub(ctx.gas_left()).get()
                # record_stats!(observe | TXN_EXECUTION_GAS_USAGE | gas_usage)
                exec_flag = True
            else:
                return discard_error_output(VMStatus(StatusCode.UNKNOWN_STATUS))
        except VMException as error:
            traceback.print_exc()
            err = error
            failed_gas_left = ctx.gas_left
            exec_flag = False
        if exec_flag:
            try:
                failed_gas_left = ctx.gas_left
                gas_free_ctx = SystemExecutionContext.From(ctx)
                self.run_epilogue(gas_free_ctx, txn_data)
                return gas_free_ctx.get_transaction_output(txn_data, VMStatus(StatusCode.EXECUTED))
            except VMException as error:
                traceback.print_exc()
                err = error
                exec_flag = False
        if exec_flag == False:
            return self.failed_transaction_cleanup(err.vm_status[0], failed_gas_left, txn_data, remote_cache)


    # Generates a transaction output for a transaction that encountered errors during the
    # execution process. This is public for now only for tests.
    def failed_transaction_cleanup(
        self,
        error_code: VMStatus,
        gas_left: GasUnits,
        txn_data: TransactionMetadata,
        remote_cache: BlockDataCache,
    ) -> TransactionOutput:
        gas_free_ctx = SystemExecutionContext.new(remote_cache, gas_left)
        ts = TransactionStatus.from_vm_status(error_code)
        if ts.tag == TransactionStatus.Keep:
            try:
                self.run_epilogue(gas_free_ctx, txn_data)
                return gas_free_ctx.get_transaction_output(txn_data, error_code)
            except VMException as err:
                traceback.print_exc()
                return discard_error_output(err.vm_status[0])
        elif ts.tag == TransactionStatus.Discard:
            return discard_error_output(error_code)
        else:
            bail("unreachable!")

    def execute_user_transaction(
        self,
        state_view: StateView,
        remote_cache: BlockDataCache,
        txn: SignatureCheckedTransaction,
    ) -> TransactionOutput:
        txn_data = TransactionMetadata.new(txn.into_inner())
        # verified_payload = record_stats! {time_hist | TXN_VERIFICATION_TIME_TAKEN | {
        #     self.verify_transaction_impl(txn, state_view, remote_cache)
        # }}
        try:
            # record_stats! {time_hist | TXN_EXECUTION_TIME_TAKEN | {

            # }}
            verified_payload = self.verify_transaction_impl(txn, state_view, remote_cache)
            result = self.execute_verified_payload(
                    remote_cache,
                    txn_data,
                    verified_payload,
                )
        except VMException as err:
            result = discard_error_output(err.vm_status[0])

        if TransactionStatus.Keep == result.status.tag:
            remote_cache.push_write_set(result.write_set)

        return result


    def process_change_set(
        self,
        remote_cache: BlockDataCache,
        change_set: ChangeSet,
    ) -> TransactionOutput:
        (write_set, events) = change_set.into_inner()
        remote_cache.push_write_set(write_set)
        self.load_configs_impl(remote_cache)
        return TransactionOutput(
            write_set,
            events,
            0,
            VMStatus(StatusCode.EXECUTED),
        )


    def process_block_prologue(
        self,
        remote_cache: BlockDataCache,
        block_metadata: BlockMetadata,
    ) -> TransactionOutput:
        # TODO: How should we setup the metadata here? A couple of thoughts here:
        # 1. We might make the txn_data to be poisoned so that reading anything will result in a panic.
        # 2. The most important consideration is figuring out the sender address.  Having a notion of a
        #    "null address" (probably 0x0...0) that is prohibited from containing modules or resources
        #    might be useful here.
        # 3. We set the max gas to a big number just to get rid of the potential out of gas error.
        txn_data = TransactionMetadata.default()
        txn_data.sender = CORE_CODE_ADDRESS
        txn_data.max_gas_amount = GasUnits.new(Uint64.max_value)

        interpreter_context =\
            TransactionExecutionContext.new(txn_data.max_gas_amount, remote_cache)
        # TODO: We might need a non zero cost table here so that we can at least bound the execution
        #       time by a reasonable amount.
        gas_schedule = CostTable.zero()

        args = [
            Value.Uint64(block_metadata.round),
            Value.Uint64(block_metadata.timestamp_usecs),
            Value.vector_address(block_metadata.previous_block_votes),
            Value.address(block_metadata.proposer),
        ]
        try:
            self.move_vm.execute_function(
                LIBRA_BLOCK_MODULE,
                BLOCK_PROLOGUE,
                gas_schedule,
                interpreter_context,
                txn_data,
                args,
            )
            output = interpreter_context\
                .get_transaction_output(txn_data, VMStatus(StatusCode.EXECUTED))
            remote_cache.push_write_set(output.write_set)
            return output
        except Exception:
            traceback.print_exc()
            raise

    # Run the prologue of a transaction by calling into `PROLOGUE_NAME` function stored
    # in the `ACCOUNT_MODULE` on chain.
    def run_prologue(
        self,
        chain_state: ChainState,
        txn_data: TransactionMetadata,
    ) -> None:
        txn_sequence_number = txn_data.sequence_number
        txn_public_key = txn_data.authentication_key_preimage
        txn_gas_price = txn_data.gas_unit_price.get()
        txn_max_gas_units = txn_data.max_gas_amount.get()
        txn_expiration_time = txn_data.expiration_time
        # record_stats! {time_hist | TXN_PROLOGUE_TIME_TAKEN | {
        try:
            self.move_vm.execute_function(
                ACCOUNT_MODULE,
                PROLOGUE_NAME,
                self.get_gas_schedule(),
                chain_state,
                txn_data,
                [
                    Value.Uint64(txn_sequence_number),
                    Value.vector_u8(txn_public_key),
                    Value.Uint64(txn_gas_price),
                    Value.Uint64(txn_max_gas_units),
                    Value.Uint64(txn_expiration_time),
                ],
            )
        except VMException as err:
            traceback.print_exc()
            # chain_state.data_view.data_cache.data_view.print_account_resource()
            ret = convert_prologue_runtime_error(err.vm_status[0], txn_data.sender)
            raise VMException(ret)



    # Run the epilogue of a transaction by calling into `EPILOGUE_NAME` function stored
    # in the `ACCOUNT_MODULE` on chain.
    def run_epilogue(
        self,
        chain_state: ChainState,
        txn_data: TransactionMetadata,
    ) -> None:
        txn_sequence_number = txn_data.sequence_number
        txn_gas_price = txn_data.gas_unit_price.get()
        txn_max_gas_units = txn_data.max_gas_amount.get()
        gas_remaining = chain_state.remaining_gas().get()
        # record_stats! {time_hist | TXN_EPILOGUE_TIME_TAKEN | {

        self.move_vm.execute_function(
            ACCOUNT_MODULE,
            EPILOGUE_NAME,
            self.get_gas_schedule(),
            chain_state,
            txn_data,
            [
                Value.Uint64(txn_sequence_number),
                Value.Uint64(txn_gas_price),
                Value.Uint64(txn_max_gas_units),
                Value.Uint64(gas_remaining),
            ],
        )


    def execute_block_impl(
        self,
        transactions: List[Transaction],
        state_view: StateView,
    ) -> List[TransactionOutput]:
        count = transactions.__len__()
        result = []
        blocks = chunk_block_transactions(transactions)
        data_cache = BlockDataCache.new(state_view)
        self.load_configs_impl(data_cache)
        for block in blocks:
            if block.UserTransaction:
                outs =\
                    self.execute_user_transactions(block.value, data_cache, state_view)
                result.extend(outs)
            elif block.BlockPrologue:
                result.append(self.process_block_prologue(data_cache, block.value))
            elif block.WriteSet:
                self.check_change_set(change_set, state_view)
                out = self.process_change_set(data_cache, change_set)
                # .unwrap_or_else(discard_error_output)
                result.append(out)

        report_block_count(count)
        return result


    def execute_user_transactions(
        self,
        txn_block: List[SignedTransaction],
        data_cache: BlockDataCache,
        state_view: StateView,
    ) -> List[TransactionOutput]:
        signature_verified_block = [self.check_txn_signature(x) for x in txn_block]
        result = []
        for txn in signature_verified_block:
            # record_stats! {time_hist | TXN_TOTAL_TIME_TAKEN | {
            if isinstance(txn, SignatureCheckedTransaction):
                output = self.execute_user_transaction(state_view, data_cache, txn)
            else:
                output = discard_error_output(txn)

            report_execution_status(output.status)

            # `result` is initially empty, a single element is pushed per loop iteration and
            # the number of iterations is bound to the max size of `signature_verified_block`
            assert (result.__len__() < usize.max_value)
            result.append(output)

        return result


    def check_txn_signature(self, transaction: SignedTransaction) -> Union[SignatureCheckedTransaction, VMStatus]:
        try:
            signature_verified_txn = transaction.check_signature()
            return signature_verified_txn
        except Exception:
            return VMStatus(StatusCode.INVALID_SIGNATURE)



    # Validators external API
    # impl VMVerifier for LibraVM {
    # Determine if a transaction is valid. Will return `None` if the transaction is accepted,
    # `Some(Err)` if the VM rejects it, with `Err` as an error code. Verification performs the
    # following steps:
    # 1. The signature on the `SignedTransaction` matches the public key included in the
    #    transaction
    # 2. The script to be executed is under given specific configuration.
    # 3. Invokes `LibraAccount.prologue`, which checks properties such as the transaction has the
    # right sequence number and the sender has enough balance to pay for the gas.
    # TBD:
    # 1. Transaction arguments matches the main function's type signature.
    #    We don't check this item for now and would execute the check at execution time.
    def validate_transaction(
        self,
        transaction: SignedTransaction,
        state_view: StateView,
    ) -> Optional[VMStatus]:
        data_cache = BlockDataCache.new(state_view)
        # record_stats! {time_hist | TXN_VALIDATION_TIME_TAKEN | {
        try:
            signature_verified_txn = transaction.check_signature()
        except Exception:
            return VMStatus(StatusCode.INVALID_SIGNATURE)

        res = None
        try:
            self.verify_transaction_impl(signature_verified_txn, state_view, data_cache)
        except VMException as e:
            err = e.vm_status[0]
            if err.major_status == StatusCode.SEQUENCE_NUMBER_TOO_NEW:
                res = None
            else:
                res = convert_prologue_runtime_error(err, signature_verified_txn.sender)

        report_verification_status(res)
        return res


    # Executor external API
    # impl VMExecutor for LibraVM {
    # Execute a block of `transactions`. The output vector will have the exact same length as the
    # input vector. The discarded transactions will be marked as `TransactionStatus.Discard` and
    # have an empty `WriteSet`. Also `state_view` is immutable, and does not have interior
    # mutability. Writes to be applied to the data view are encoded in the write set part of a
    # transaction output.
    @classmethod
    def execute_block(cls,
        transactions: List[Transaction],
        state_view: StateView,
    ) -> List[TransactionOutput]:
        vm = cls.new()
        return vm.execute_block_impl(transactions, state_view)



def discard_error_output(err: VMStatus) -> TransactionOutput:
    # Since this transaction will be discarded, no writeset will be included.
    return TransactionOutput(
        WriteSet([]),
        [],
        0,
        TransactionStatus(TransactionStatus.Discard, err),
    )


# Internal APIs for the Libra VM, primarily used for testing.
class LibraVMInternals(LibraVM):

    # Executes the given code within the context of a transaction.
    #
    # The `TransactionExecutionContext` can be used as a `ChainState`.
    #
    # If you don't care about the transaction metadata, use `TransactionMetadata.default()`.
    def with_txn_context(
        self,
        txn_data: TransactionMetadata,
        state_view: StateView,
        f,
    ):
        remote_storage = RemoteStorage.new(state_view)
        txn_context = \
            TransactionExecutionContext.new(txn_data.max_gas_amount, remote_storage)
        return f(txn_context)


# Transactions divided by transaction flow.
# Transaction flows are different across different types of transactions.
class TransactionBlock(RustEnum):
    _enums = [
        ('UserTransaction', [SignedTransaction]),
        ('WriteSet', ChangeSet),
        ('BlockPrologue', BlockMetadata)
    ]


def chunk_block_transactions(txns: List[Transaction]) -> List[TransactionBlock]:
    blocks = []
    buf = []
    for txn in txns:
        if txn.BlockMetadata:
            if buf:
                blocks.append(TransactionBlock('UserTransaction', buf))
                buf = []
            blocks.append(TransactionBlock('BlockPrologue', txn.value))
        elif txn.WriteSet:
            if buf:
                blocks.append(TransactionBlock('UserTransaction', buf))
                buf = []
            blocks.append(TransactionBlock('WriteSet', txn.value))
        elif txn.UserTransaction:
            txn = txn.value
            if txn.payload.WriteSet:
                if buf:
                    blocks.append(TransactionBlock('UserTransaction', buf))
                    buf = []
                blocks.append(TransactionBlock('WriteSet', txn.payload.value))
            else:
                buf.append(txn)

    if buf:
        blocks.append(TransactionBlock('UserTransaction', buf))

    return blocks


class VerifiedTranscationPayload(RustEnum):
    _enums = [
        ('Script', (bytes, [TransactionArgument])),
        ('Module', bytes)
    ]


def is_allowed_script(publishing_option, program: bytes) -> bool:
    return True
    # match publishing_option {
    #     VMPublishingOption.Open | VMPublishingOption.CustomScripts => True,
    #     VMPublishingOption.Locked(whitelist) => {
    #         hash_value = HashValue.from_sha3_256(program)
    #         whitelist.contains(hash_value)
    #     }
    # }


def convert_txn_arg(arg: TransactionArgument) -> Value:
    if arg.U64:
        return Value.Uint64(arg.value)
    elif arg.Address:
        return Value.address(arg.value)
    elif arg.Bool:
        return Value.bool(arg.value)
    elif arg.U8Vector:
        return Value.vector_u8(arg.value)
    else:
        bail("unreachable!")

# Convert the transaction arguments into move values.
def convert_txn_args(args: List[TransactionArgument]) -> List[Value]:
    return [convert_txn_arg(arg) for arg in args]

