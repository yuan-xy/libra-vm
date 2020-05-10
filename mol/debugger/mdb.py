from mol.debugger.base_db import BaseDebugger, BaseDebuggerQuit, Breakpoint
from mol.move_vm.runtime.trace_help import TraceType, TraceCallback, GlobalTracer
from mol.global_source_mapping import GlobalSourceMapping
from mol.functional_tests.ir_compiler import IRCompiler
from mol.functional_tests import testsuite
from pathlib import Path


class MoveDebugger(BaseDebugger):
    def user_call(self, frame, args):
        pass

    def user_line(self, frame):
        pass

    def user_return(self, frame, retval):
        pass

    def user_exception(self, frame, exc_stuff):
        print('+++ exception', exc_stuff)
        self.set_continue()

    def run_move(self, file):
        GlobalSourceMapping.init_std_mapping()
        self.reset()
        GlobalTracer.settrace(self.trace_dispatch)
        res = None
        try:
            compiler = IRCompiler()
            compiler.output_source_maps = False
            path = Path(file)
            if path.exists():
                res = testsuite.functional_tests(compiler, file)
            else:
                print(f"File not exsits: {file}")

        except BaseDebuggerQuit:
            pass
        finally:
            self.quitting = True
            GlobalTracer.settrace(None)
        return res
