from mol.debugger.mdb import Mdb
from mol.move_vm.runtime.trace_help import TraceType, TraceCallback, GlobalTracer
from os.path import join, dirname
import sys


class Tdb(Mdb):
    def user_call(self, frame, args):
        print('call', frame.address_module_function())

    def user_line(self, frame):
        print('+++', frame.line_no, ':', frame.src_line())

    def user_return(self, frame, retval):
        print('return', frame.address_module_function(), retval)

    def user_exception(self, frame, exc_stuff):
        print('+++ exception', exc_stuff)
        self.set_continue()



def test_mdb(capsys):
    t = Tdb()
    curdir = dirname(__file__)
    filename = join(curdir, "../../ir-testsuite/tests/examples/transfer_money.mvir")
    t.run_move(filename)
    output = capsys.readouterr().out
    assert output.startswith("call ('00000000000000000000000000000000', 'LibraAccount', 'prologue')")
    assert "'<SELF>', 'main'" in output
    assert output.endswith("return ('00000000000000000000000000000000', 'LibraAccount', 'epilogue') []\n")

