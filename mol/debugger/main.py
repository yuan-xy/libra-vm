#!/usr/bin/env python3
import argparse
import os
import signal
import sys

from mol.debugger.color import support_color, print_color, bcolors
from mol.debugger.command import get_commands_alias, parse_cmd, report_error, print_commands
from mol.debugger.query_commands import QueryCommand
from mol.debugger.transfer_commands import TransferCommand
import readline
from mol.debugger.mdb import MoveDebugger



version = "0.1.0"


def get_commands():
    commands = [QueryCommand(), TransferCommand()]
    return get_commands_alias(commands)


def run_shell(args):
    source_path = args.source_path[0]
    print(source_path)
    mdb = MoveDebugger()
    mdb.run_move(source_path)
    return
    context = {}
    (commands, alias_to_cmd) = get_commands()
    while True:
        prompt = "libra% "
        if support_color():
            prompt = f'\033[91m{prompt}\033[0m'
        try:
            line = input(prompt)
        except EOFError:
            sys.exit(0)
        params = parse_cmd(line)
        if len(params) == 0:
            continue
        cmd = alias_to_cmd.get(params[0])
        if cmd is not None:
            cmd.execute(context, params)
        else:
            if params[0] == "quit" or params[0] == "q!":
                break
            elif params[0] == "help" or params[0] == "h":
                print_help(commands)
            else:
                print(f"Unknown command: {params[0]}")


def print_help(commands):
    print("usage: <command> <args>\n\nUse the following commands:\n")
    print_commands(commands)
    print_color("help | h", bcolors.OKGREEN)
    print("\tPrints this help")
    print_color("quit | q!", bcolors.OKGREEN)
    print("\tExit this client")
    print("\n")


def get_parser():
    parser = argparse.ArgumentParser(prog='librad')
    parser.add_argument('source_path', nargs=1,
                        help='Path to the Move IR source file to debug')
    parser.add_argument('-v', "--verbose", action='store_true',
                        default=False, help='Verbose output.')
    parser.add_argument('-V', '--version', action='version',
                        version=f'Libra VM Debugger {version}')
    return parser


def handler(signum, frame):
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    #signal.signal(signal.SIGTSTP, handler)
    if os.name == 'posix':
        readline.set_history_length(1000)
    parser = get_parser()
    libra_args = parser.parse_args(sys.argv[1:])
    try:
        run_shell(libra_args)
    except Exception as err:
        report_error("some error occured", err, libra_args.verbose)


if __name__ == '__main__':
    main()
