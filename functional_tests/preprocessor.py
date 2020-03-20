from __future__ import annotations
from functional_tests.checker import Directive
from functional_tests.common import LineSp
from functional_tests.config.block_metadata import Entry as BlockEntry
from functional_tests.config.block_metadata import build_block_metadata, is_new_block
from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.config.globl import Entry as GlobalConfigEntry
from functional_tests.config.transaction import Config as TransactionConfig
from functional_tests.config.transaction import Entry as TransactionConfigEntry
from functional_tests.config.transaction import is_new_transaction
from functional_tests.errors import *
from functional_tests.evaluator import Command, Transaction
import re

PAT = re.compile(r"\{\{([A-Za-z][A-Za-z0-9]*)\}\}")

# Substitutes the placeholders (account names in double curly brackets) with addresses.
def substitute_addresses(config: GlobalConfig, text: str) -> str:
    def lambda0(m):
        name = m.group(1)
        return format_str("0x{}", config.get_account_for_name(name).address())

    return PAT.subn(lambda0, text)



@dataclass
class RawTransactionInput:
    config_entries: List[TransactionConfigEntry]
    text: List[str]


@dataclass
class RawCommand:
    tag: int
    value: Union[RawTransactionInput, List[BlockEntry]]

    vTransaction = 1
    vBlockMetadata = 2


def is_empty_command(cmd: RawCommand) -> bool:
    if cmd.tag == RawCommand.vTransaction:
        txn = cmd.value
        return not txn.text and not txn.config_entries
    else:
        return not cmd.value


def check_raw_transaction(txn: RawTransactionInput) -> None:
    if not txn.text:
        if txn.config_entries:
            raise ErrorKind.Other(
                "config options attached to empty transaction"
            )

        raise ErrorKind.Other("empty transaction")



def check_raw_command(cmd: RawCommand) -> None:
    if cmd.tag == RawCommand.vTransaction:
        check_raw_transaction(cmd.value)
    elif cmd.tag == RawCommand.vBlockMetadata:
        entries = cmd.value
        if entries.__len__() < 2:
            raise ErrorKind.Other("block prologue doesn't have enough arguments")


def new_command(ins: str) -> Optional[RawCommand]:
    if is_new_transaction(ins):
        return RawCommand(RawCommand.vTransaction, RawTransactionInput(
            config_entries= [],
            text= [],
        ))

    if is_new_block(ins):
        return RawCommand(RawCommand.vBlockMetadata, [])

    return None


# Parses the input string into three parts: a global config, directives and transactions.
def split_input(
    lines: List[str],
) -> Tuple[
    List[GlobalConfigEntry],
    List[LineSp],
    List[RawCommand],
]:
    lines = [x for x in lines if x]
    global_config = []
    directives = []
    commands = []
    first_transaction = True

    command = RawCommand(RawCommand.vTransaction, RawTransactionInput(
        config_entries= [],
        text= [],
    ))

    for (line_idx, line) in enumerate(lines):
        line = line
        nc = new_command(line)
        if nc:
            if first_transaction and is_empty_command(command):
                command = nc
                continue

            check_raw_command(command)
            commands.append(command)
            command = nc
            first_transaction = False
            continue

        entry = GlobalConfigEntry.try_parse(line)
        if entry:
            global_config.append(entry)
            continue

        dirs = Directive.try_parse(line)
        if dirs:
            directives.extend([sp.into_line_sp(line_idx) for sp in dirs])
            continue

        if command.tag == RawCommand.vTransaction:
            txn = command.value
            entry = TransactionConfigEntry.try_parse(line)
            if entry:
                txn.config_entries.append(entry)
                continue

            if line.strip():
                # breakpoint()
                txn.text.append(line)
                continue

        elif command.tag == RawCommand.vBlockMetadata:
            entries = command.value
            entry = BlockEntry.from_str(line)
            if entry:
                entries.append(entry)
                continue

    check_raw_command(command)
    commands.append(command)

    return (global_config, directives, commands)


def build_transactions(
    config: GlobalConfig,
    command_inputs: List[RawCommand],
) -> List[Command]:

    def lambda0(command_input):
        if command_input.tag == RawCommand.vTransaction:
            txn_input = command_input.value
            return Command(Command.vTransaction, Transaction(
                TransactionConfig.build(config, txn_input.config_entries),
                substitute_addresses(config, "\n".join(txn_input.text)),
            ))
        elif command_input.tag == RawCommand.vBlockMetadata:
            return Command(Command.vBlockMetadata, build_block_metadata(
                            config, command_input.value,
                        ))
        else:
            bail("unreachable!")

    return [lambda0(x) for x in command_inputs]

