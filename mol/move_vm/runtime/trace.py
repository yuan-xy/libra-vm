#!/usr/bin/env python3

import argparse, sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from typing import Callable, Union, Any, Tuple
from mol.functional_tests import testsuite
from mol.functional_tests.ir_compiler import IRCompiler
from mol.move_vm.runtime.trace_help import TraceType, TraceCallback, GlobalTracer
from mol.stdlib import stdlib_modules


def print_function(amf: Tuple[str, str, str]) -> str:
    (a, m, f) = amf
    return a[0:4] +"..."+ a[-5:-1] + f" {m}::{f}"


class Trace:
    def __init__(self, count, trace, countfuncs, countcallers, bytecode):
        self.counts = {}   # keys are (filename, linenumber)
        self.donothing = False
        self.trace = trace
        self.bytecode = bytecode
        self._calledfuncs = {}
        self._callers = {}
        self._caller_cache = {}
        if countcallers:
            self.globaltrace = self.globaltrace_trackcallers
        elif countfuncs:
            self.globaltrace = self.globaltrace_countfuncs
        elif trace and count:
            self.globaltrace = self.globaltrace_lt
            self.localtrace = self.localtrace_trace_and_count
        elif trace:
            self.globaltrace = self.globaltrace_lt
            self.localtrace = self.localtrace_trace
        elif count:
            self.globaltrace = self.globaltrace_lt
            self.localtrace = self.localtrace_count
        else:
            # Ahem -- do nothing?  Okay.
            self.donothing = True

    def globaltrace_trackcallers(self, frame, why, arg):
        """Handler for call events.

        Adds information about who called who to the self._callers dict.
        """
        if why == TraceType.CALL:
            print(frame.source_filename())
            print(frame.executable_linenos())
            #TTODO: support native call
            this_func = frame.address_module_function()
            parent = frame.f_back
            if parent is None:
                parent_func = ("", "", "<Entrypoint>")
            else:
                parent_func = parent.address_module_function()
            print(print_function(parent_func), " --> ", print_function(this_func))
            self._callers[(parent_func, this_func)] = 1

    def globaltrace_countfuncs(self, frame, why, arg):
        """Handler for call events.

        Adds (filename, modulename, funcname) to the self._calledfuncs dict.
        """
        if why == TraceType.CALL:
            this_func = frame.address_module_function()
            print(this_func)
            self._calledfuncs[this_func] = 1

    def globaltrace_lt(self, frame, why, arg):
        """Handler for call events.

        If the code block being entered is to be ignored, returns `None',
        else returns self.localtrace.
        """
        if why == TraceType.RETURN:
            this_func = frame.address_module_function()
            def ignore():
                address, _, _ = this_func
                return False
                return address == '00000000000000000000000000000000'
            if not ignore():
                if self.trace:
                    print("RETURN ->",this_func)

        if why == TraceType.CALL:
            this_func = frame.address_module_function()
            def ignore():
                address, _, _ = this_func
                return False
                return address == '00000000000000000000000000000000'
            if not ignore():
                if self.trace:
                    print(this_func)
                if self.bytecode:
                    return self.localtrace, self.opcode_trace
                else:
                    return self.localtrace
            else:
                return None

    def localtrace_trace_and_count(self, frame, why, arg):
        if why == TraceType.LINE:
            print("\t", arg[0], arg[1])
            this_func = frame.address_module_function()
            key = this_func, frame.pc
            self.counts[key] = self.counts.get(key, 0) + 1
        return self.localtrace

    def localtrace_trace(self, frame, why, arg):
        if why == TraceType.LINE:
            print("\t", arg[0], arg[1])
        return self.localtrace

    def localtrace_count(self, frame, why, arg):
        if why == TraceType.LINE:
            this_func = frame.address_module_function()
            key = this_func, frame.pc
            self.counts[key] = self.counts.get(key, 0) + 1
        return self.localtrace

    def opcode_trace(self, frame, why, arg):
        if why == TraceType.OPCODE:
            print("\t", arg[0], arg[1])
        return self.opcode_trace


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='trace 1.0')

    grp = parser.add_argument_group('Main options',
            'One of these (or --report) must be given')

    grp.add_argument('-c', '--count', action='store_true',
            help='Count the number of times each line is executed and write '
                 'the counts to <module>.cover for each module executed, in '
                 'the module\'s directory. See also --coverdir, --file, '
                 '--no-report below.')
    grp.add_argument('-t', '--trace', action='store_true',
            help='Print each line to sys.stdout before it is executed')
    grp.add_argument('-b', '--bytecode', action='store_true',
            help='Print each bytecode before it is executed')
    grp.add_argument('-l', '--listfuncs', action='store_true',
            help='Keep track of which functions are executed at least once '
                 'and write the results to sys.stdout after the program exits. '
                 'Cannot be specified alongside --trace or --count.')
    grp.add_argument('-T', '--trackcalls', action='store_true',
            help='Keep track of caller/called pairs and write the results to '
                 'sys.stdout after the program exits.')

    # grp = parser.add_argument_group('Filters',
    #         'Can be specified multiple times')
    # grp.add_argument('--ignore-module', action='append', default=[],
    #         help='Ignore the given module(s) and its submodules '
    #              '(if it is a package). Accepts comma separated list of '
    #              'module names.')
    # grp.add_argument('--ignore-dir', action='append', default=[],
    #         help='Ignore files in the given directory '
    #              '(multiple directories can be joined by os.pathsep).')

    parser.add_argument('progname', nargs='?',
            help='file to run as main program')
    parser.add_argument('arguments', nargs=argparse.REMAINDER,
            help='arguments to the program')

    opts = parser.parse_args()

    # opts.ignore_module = [mod.strip()
    #                       for i in opts.ignore_module for mod in i.split(',')]

    if not any([opts.trace, opts.count, opts.listfuncs, opts.trackcalls]):
        parser.error('must specify one of --trace, --count, --report, '
                     '--listfuncs, or --trackcalls')

    if opts.listfuncs and (opts.count or opts.trace):
        parser.error('cannot specify both --listfuncs and (--trace or --count)')

    if opts.progname is None:
        parser.error('progname is missing: required with the main options')

    tracer = Trace(opts.count, opts.trace, countfuncs=opts.listfuncs,
              countcallers=opts.trackcalls, bytecode=opts.bytecode)

    if not tracer.donothing:
        GlobalTracer.settrace(tracer.globaltrace)

    try:
        compiler = IRCompiler()
        testsuite.functional_tests(compiler, opts.progname)
    finally:
        if not tracer.donothing:
            GlobalTracer.settrace(None)

    if opts.count:
        for k, v in tracer.counts.items():
            print(k, v)

if __name__=='__main__':
    main()
