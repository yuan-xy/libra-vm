#!/usr/bin/env python3
import argparse
import os
import signal
import sys
from mol.debugger.mdb import Mdb


version = "0.1.0"

def run_shell(args):
    source_path = args.source_path[0]
    print(source_path)
    mdb = Mdb()
    mdb.run_move(source_path)

def get_parser():
    parser = argparse.ArgumentParser(prog='debugger')
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
    parser = get_parser()
    debug_args = parser.parse_args(sys.argv[1:])
    run_shell(debug_args)


if __name__ == '__main__':
    main()
