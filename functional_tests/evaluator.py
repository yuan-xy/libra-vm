from __future__ import annotations
from functional_tests.lib import Stage
from functional_tests.compiler import Compiler, ScriptOrModule
from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.config.transaction import Config as TransactionConfig
from functional_tests.errors import *
from bytecode_verifier.verifier import (
    verify_module_dependencies, verify_script_dependencies, VerifiedModule, VerifiedScript,
    VerifyException
)
from e2e_tests.executor import FakeExecutor, VMPublishingOption
from libra.crypto.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from libra_storage.state_view import StateView
from libra import AccessPath, Address
from libra.block_metadata import BlockMetadata
from libra.language_storage import ModuleId
from libra.transaction import Module as TransactionModule
from libra.transaction import Script as TransactionScript
from libra.transaction import Transaction as LibraTransaction
from libra.transaction import RawTransaction, SignedTransaction, TransactionOutput, TransactionStatus, TransactionPayload
from libra.vm_error import StatusCode, VMStatus
from libra_vm import CompiledModule, CompiledScript, ModuleView
from libra_vm.gas_schedule import GasAlgebra, MAXIMUM_NUMBER_OF_GAS_UNITS
from dataclasses import dataclass, field
from libra.rustlib import usize, bail, flatten, format_str
from typing import Any, List, Optional, Mapping, Union
from enum import IntEnum
from canoser import Uint64
import traceback

# A transaction to be evaluated by the testing infra.
# Contains code and a transaction config.
@dataclass
class Transaction:
    config: TransactionConfig
    ins: str

    def __init__(self, config, ins):
        self.config = config
        if isinstance(ins, str):
            self.ins = ins
        else:
            bail("unreachable!")


# Commands that drives the operation of LibraVM. Such as:
# 1. Execute user transaction
# 2. Publish a new block metadata
#
# In the future we will add more commands to mimic the full public API of LibraVM,
# including reloading the on-chain configuration that will affect the code path for LibraVM,
# cleaning the cache in the LibraVM, etc.
@dataclass
class Command:
    tag: int
    value: Union[Transaction, BlockMetadata]

    vTransaction = 1
    vBlockMetadata = 2


# Evaluation status: success or failure.
class Status(IntEnum):
    Success = 1
    Failure = 2


@dataclass
class OutputType:
    tag: int
    value: Any

    vCompiledModule = 1 #(Box<CompiledModule>),
    vCompiledScript = 2 #(Box<CompiledScript>),
    vCompilerLog    = 3 #(String),
    vTransactionOutput = 4 #(Box<TransactionOutput>),


    @classmethod
    def CompiledModule(cls, v):
        return cls(cls.vCompiledModule, v)

    @classmethod
    def CompiledScript(cls, v):
        return cls(cls.vCompiledScript, v)

    @classmethod
    def CompilerLog(cls, v):
        return cls(cls.vCompilerLog, v)

    @classmethod
    def TransactionOutput(cls, v):
        return cls(cls.vTransactionOutput, v)


    def to_check_string(self) -> str:
        return format_str("{}", self)


TransactionId = usize

# An entry in the `EvaluationLog`.
@dataclass
class EvaluationOutput:
    tag: int
    value: Any

    vTransaction = 1 #(TransactionId),
    vStage       = 2 #(Stage),
    vOutput      = 3 #(OutputType),
    vError       = 4 #(Box<Error>),
    vStatus      = 5 #(Status),

    @classmethod
    def Transaction(cls, v):
        return cls(cls.vTransaction, v)

    @classmethod
    def Stage(cls, v):
        return cls(cls.vStage, v)

    @classmethod
    def Output(cls, v):
        return cls(cls.vOutput, v)

    @classmethod
    def Error(cls, v):
        return cls(cls.vError, v)

    @classmethod
    def Status(cls, v):
        return cls(cls.vStatus, v)


    def is_error(self) -> bool:
        return self.tag == EvaluationOutput.vError


    def __str__(self) -> str:
        if self.tag == EvaluationOutput.vTransaction:
            return format_str("Transaction {}", self.value)
        elif self.tag == EvaluationOutput.vStage:
            return format_str("Stage: {}", self.value)
        elif self.tag == EvaluationOutput.vOutput:
            return self.value.value.__str__()
        elif self.tag == EvaluationOutput.vError:
            return format_str("Error: {}", self.value)
        elif self.tag == EvaluationOutput.vStatus:
            return format_str("Status: {}", self.value)
        else:
            bail("unreachable!")



# A log consisting of outputs from all stages and the final status.
# This is checked against the directives.
@dataclass
class EvaluationLog:
    outputs: List[EvaluationOutput] = field(default_factory=list)

    def __str__(self) -> str:
        ret = ""
        for i, output in enumerate(self.outputs):
            ret += format_str("[{}] {}", i, output)
        return ret


    def get_failed_transactions(self) -> List[Tuple[usize, Stage]]:
        res = []
        last_txn = None
        last_stage = None

        for output in self.outputs:
            if output.tag == EvaluationOutput.vTransaction:
                last_txn = output.value
            elif output.tag == EvaluationOutput.vStage:
                last_stage = output.value
            elif output.tag == EvaluationOutput.vStatus:
                if output.value == Status.Failure:
                    if last_txn and last_stage:
                        res.append((last_txn, last_stage))
                    else:
                        bail("unreachable!")
            else:
                pass

        return res


    def append(self, output: EvaluationOutput):
        self.outputs.append(output)




def fetch_script_dependencies(
    fexec: FakeExecutor,
    script: CompiledScript,
) -> List[VerifiedModule]:
    module = script.into_module()
    return fetch_module_dependencies(fexec, module)


def fetch_module_dependencies(
    fexec: FakeExecutor,
    module: CompiledModule,
) -> List[VerifiedModule]:
    idents = [x.module_id() for x in ModuleView.new(module).module_handles()]
    for x in idents:
        if x.address == module.address() and x.name == module.name():
            idents.remove(x)
    return fetch_dependencies(fexec, idents)


def fetch_dependencies(
    fexec: FakeExecutor,
    idents: List[ModuleId],
) -> List[VerifiedModule]:
    # idents.into_inner().
    return flatten([fetch_dependency(fexec, ident) for ident in idents])


def fetch_dependency(fexec: FakeExecutor, ident: ModuleId) -> Optional[VerifiedModule]:
    ap = ident.into()
    blob = fexec.get_state_view().get(ap)
    compiled: CompiledModule = CompiledModule.deserialize(blob)
    return VerifiedModule.new(compiled)


# Verify a script with its dependencies.
def verify_script(
    script: CompiledScript,
    deps: List[VerifiedModule],
) -> VerifiedScript:
    verified_script = VerifiedScript.new(script)
    errs = verify_script_dependencies(verified_script, deps)
    if errs:
        raise VerifyException(errs)

    return verified_script


# Verify a module with its dependencies.
def verify_module(
    module: CompiledModule,
    deps: List[VerifiedModule],
) -> VerifiedModule:
    verified_module = VerifiedModule.new(module)
    errs = verify_module_dependencies(verified_module, deps)
    if errs:
        raise VerifyException(errs)

    return verified_module


# A set of common parameters required to create transactions.
@dataclass
class TransactionParameters:
    sender_addr: Address
    pubkey: Ed25519PublicKey
    privkey: Ed25519PrivateKey
    sequence_number: Uint64
    max_gas_amount: Uint64
    gas_unit_price: Uint64
    expiration_time: Uint64


# Gets the transaction parameters from the current execution environment and the config.
def get_transaction_parameters(
    fexec: FakeExecutor,
    config: TransactionConfig,
) -> TransactionParameters:
    account_resource = fexec.read_account_resource(config.sender)
    sequence_number = config.sequence_number
    if sequence_number is None:
        sequence_number = account_resource.sequence_number

    max_gas = config.max_gas
    if max_gas is None:
        max_gas = min(
                        MAXIMUM_NUMBER_OF_GAS_UNITS.get(),
                        account_resource.balance,
                    )
    expiration_time = config.expiration_time
    if expiration_time is None:
        expiration_time = 40000

    return TransactionParameters(
        sender_addr= config.sender.address(),
        pubkey= config.sender.pubkey,
        privkey= config.sender.privkey,
        sequence_number= sequence_number,

        max_gas_amount= max_gas,
        gas_unit_price= 1,
        # TTL is 86400s. Initial time was set to 0.
        expiration_time= expiration_time,
    )


# Creates and signs a script transaction.
def make_script_transaction(
    fexec: FakeExecutor,
    config: TransactionConfig,
    script: CompiledScript,
) -> SignedTransaction:
    blob = script.serialize()
    script = TransactionScript(blob, config.args)

    params = get_transaction_parameters(fexec, config)
    raw = RawTransaction(
        params.sender_addr,
        params.sequence_number,
        TransactionPayload('Script', script),
        params.max_gas_amount,
        params.gas_unit_price,
        params.expiration_time,
    )
    return raw.sign(params.privkey, params.pubkey).into_inner()


# Creates and signs a module transaction.
def make_module_transaction(
    fexec: FakeExecutor,
    config: TransactionConfig,
    module: CompiledModule,
) -> SignedTransaction:
    blob = module.serialize()
    module = TransactionModule(blob)
    params = get_transaction_parameters(fexec, config)

    raw = RawTransaction(
        params.sender_addr,
        params.sequence_number,
        TransactionPayload('Module', module),
        params.max_gas_amount,
        params.gas_unit_price,
        params.expiration_time,
    )
    return raw.sign(params.privkey, params.pubkey).into_inner()


# Runs a single transaction using the fake executor.
def run_transaction(
    fexec: FakeExecutor,
    transaction: SignedTransaction,
) -> TransactionOutput:
    outputs = fexec.execute_block([transaction])
    if outputs.__len__() == 1:
        output = outputs.pop()

        if output.status.tag == TransactionStatus.Keep:
            vmstatus = output.status.vm_status
            fexec.apply_write_set(output.write_set)
            if vmstatus.major_status == StatusCode.EXECUTED:
                return output
            else:
                raise ErrorKind(ErrorKindTag.VMExecutionFailure, output)

        elif output.status.tag == TransactionStatus.Discard:
            assert (not output.write_set.write_set)
            raise ErrorKind(ErrorKindTag.DiscardedTransaction, output)
        else:
            bail("unreachable!")
    else:
        bail("transaction outputs size mismatch")


# Serializes the script then deserializes it.
def serialize_and_deserialize_script(script: CompiledScript) -> None:
    script_blob = script.serialize()
    deserialized_script = CompiledScript.deserialize(script_blob)

    if script != deserialized_script:
        raise ErrorKind.Other(
            "deserialized script different from original one"
        )


# Serializes the module then deserializes it.
def serialize_and_deserialize_module(module: CompiledModule) -> None:
    module_blob = module.serialize()
    deserialized_module = CompiledModule.deserialize(module_blob)

    if module != deserialized_module:
        raise ErrorKind.Other(
            "deserialized module different from original one",
        )


def eval_transaction(
    compiler: Compiler,
    fexec: FakeExecutor,
    idx: usize,
    transaction: Transaction,
    log: EvaluationLog,
) -> Status:
    # Unwrap the given results. Upon failure, logs the error and aborts.
    def unwrap_or_abort(res):
        return res
        # ($res: expr) => {{
        #     match $res {
        #         Ok(r) => r,
        #         Err(e) => {
        #             log.append(EvaluationOutput.Error(Box.new(e)))
        #             return Ok(Status.Failure)


    sender_addr = transaction.config.sender.address()

    # Start processing a new transaction.
    log.append(EvaluationOutput.Transaction(idx))

    # stage 1: Compile the script/module
    if transaction.config.is_stage_disabled(Stage.Compiler):
        return Status.Success

    log.append(EvaluationOutput.Stage(Stage.Compiler))
    compiler_log = lambda s: log.append(EvaluationOutput.Output(OutputType.CompilerLog(s)))
    try:
        parsed_script_or_module =\
            unwrap_or_abort(compiler.compile(compiler_log, sender_addr, transaction.ins))
    except Exception as err:
        log.append(EvaluationOutput.Error(err))
        return Status.Failure

    compiled_script = parsed_script_or_module.script
    if compiled_script:
        log.append(EvaluationOutput.Output(OutputType.CompiledScript(
            compiled_script),
        ))

        # stage 2: verify the script
        if transaction.config.is_stage_disabled(Stage.Verifier):
            return Status.Success

        log.append(EvaluationOutput.Stage(Stage.Verifier))
        deps = fetch_script_dependencies(fexec, compiled_script)
        try:
            compiled_script = verify_script(compiled_script, deps).into_inner()
        except VerifyException as error:
            errs = error.vm_status
            for err in errs:
                err = ErrorKind.VerificationError(err)
                log.append(EvaluationOutput.Error(err))

            return Status.Failure

        # stage 3: serializer round trip
        if not transaction.config.is_stage_disabled(Stage.Serializer):
            log.append(EvaluationOutput.Stage(Stage.Serializer))
            try:
                unwrap_or_abort(serialize_and_deserialize_script(compiled_script))
            except ErrorKind as kind:
                log.append(EvaluationOutput.Error(kind.value))
                return Status.Failure

        # stage 4: execute the script
        if transaction.config.is_stage_disabled(Stage.Runtime):
            return Status.Success

        log.append(EvaluationOutput.Stage(Stage.Runtime))
        script_transaction =\
            make_script_transaction(fexec, transaction.config, compiled_script)

        try:
            txn_output = unwrap_or_abort(run_transaction(fexec, script_transaction))
        except ErrorKind as kind:
            log.append(EvaluationOutput.Error(kind.value))
            return Status.Failure

        log.append(EvaluationOutput.Output(OutputType.TransactionOutput(
            txn_output,
        )))
    else:
        compiled_module = parsed_script_or_module.module

        log.append(EvaluationOutput.Output(OutputType.CompiledModule(
            compiled_module
        )))

        # stage 2: verify the module
        if transaction.config.is_stage_disabled(Stage.Verifier):
            return Status.Success

        log.append(EvaluationOutput.Stage(Stage.Verifier))
        deps = fetch_module_dependencies(fexec, compiled_module)

        try:
            compiled_module = verify_module(compiled_module, deps).into_inner()
        except VerifyException as error:
            errs = error.vm_status
            for err in errs:
                err = ErrorKind.VerificationError(err)
                log.append(EvaluationOutput.Error(err))

            return Status.Failure

        # stage 3: serializer round trip
        if not transaction.config.is_stage_disabled(Stage.Serializer):
            log.append(EvaluationOutput.Stage(Stage.Serializer))
            unwrap_or_abort(serialize_and_deserialize_module(compiled_module))

        # stage 4: publish the module
        if transaction.config.is_stage_disabled(Stage.Runtime):
            return Status.Success

        log.append(EvaluationOutput.Stage(Stage.Runtime))
        module_transaction =\
            make_module_transaction(fexec, transaction.config, compiled_module)
        txn_output = unwrap_or_abort(run_transaction(fexec, module_transaction))
        log.append(EvaluationOutput.Output(OutputType.TransactionOutput(
            txn_output
        )))

    return Status.Success


def eval_block_metadata(
    executor: FakeExecutor,
    block_metadata: BlockMetadata,
    log: EvaluationLog,
) -> Status:
    txn = LibraTransaction('BlockMetadata', block_metadata)
    try:
        outputs = executor.execute_transaction_block([txn])
        output = outputs.pop()
        executor.apply_write_set(output.write_set)
        log.append(EvaluationOutput.Output(OutputType.TransactionOutput(
            output,
        )))
        return Status.Success
    except Exception as err:
        traceback.print_exc()
        breakpoint()
        err = ErrorKind(ErrorKindTag.VerificationError, err)
        log.append(EvaluationOutput.Error(err))
        return Status.Failure



# Feeds all given transactions through the pipeline and produces an EvaluationLog.
def eeval(
    config: GlobalConfig,
    compiler: Compiler,
    commands: List[Command],
) -> EvaluationLog:
    log = EvaluationLog()

    # Set up a fake executor with the genesis block and create the accounts.
    if not config.validator_set:
        # use the default validator set. this uses a precomputed validator set and is cheap
        fexec = FakeExecutor.custom_genesis(compiler.stdlib(), None, VMPublishingOption.Open)
    else:
        # use custom validator set. this requires dynamically generating a new genesis tx and
        # is thus more expensive.
        fexec = FakeExecutor.custom_genesis(
            compiler.stdlib(),
            config.validator_set,
            VMPublishingOption.Open,
        )

    for data in config.accounts.values():
        fexec.add_account_data(data)


    for (idx, command) in enumerate(commands):
        if command.tag == Command.vTransaction:
            transaction = command.value
            status = eval_transaction(compiler, fexec, idx, transaction, log)
            log.append(EvaluationOutput.Status(status))
        elif command.tag == Command.vBlockMetadata:
            block_metadata = command.value
            status = eval_block_metadata(fexec, block_metadata, log)
            log.append(EvaluationOutput.Status(status))

    return log