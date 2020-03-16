import os, sys
from os import listdir
from os.path import isfile, join, abspath, dirname
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from libra.access_path import AccessPath
from libra.account_address import Address
from libra.identifier import IdentStr, Identifier
from libra.language_storage import ModuleId, StructTag
from bytecode_verifier import VerifiedModule
from libra_storage.state_view import StateView, EmptyStateView
from libra_vm.gas_schedule import CostTable, GasAlgebra, GasUnits
from libra_vm.transaction_metadata import TransactionMetadata
from libra_vm.runtime.chain_state import TransactionExecutionContext
from libra_vm.runtime.data_cache import BlockDataCache
from libra_vm.runtime.move_vm import MoveVM
from canoser import Uint8
from typing import List, Optional
import cProfile

# Entry point for the bench, provide a function name to invoke in Module Bench in bench.move.
def bench(fun: str):
    # module = compile_module()
    module = deserialize_module()
    move_vm = MoveVM.new()
    move_vm.cache_module(module)
    execute(move_vm, fun)

def deserialize_module() -> VerifiedModule:
    from libra_vm.file_format import CompiledModule
    curdir = dirname(__file__)
    filename = join(curdir, "transaction_0_module_Bench.mv")
    with open(filename, 'rb') as file:
        code = file.read()
        obj = CompiledModule.deserialize(code)
        bstr = obj.serialize()
        assert code == bstr
        return VerifiedModule(obj)

# Compile `bench.move`
# def compile_module() -> VerifiedModule {
#     # TODO: this has only been tried with `cargo bench` from `libra/src/language/benchmarks`
#     path = PathBuf.from(env!("CARGO_MANIFEST_DIR"))
#     path.push("src/bench.move")
#     s = path.to_str().expect("no path specified").to_owned()

#     (_, modules) =
#         move_lang.move_compile(&[s], &[], Some(Address.default())).expect("Error compiling...")
#     match modules.remove(0) {
#         CompiledUnit.Module(_, module) => {
#             VerifiedModule.new(module).expect("Cannot verify code in file")
#         }
#         _ => panic!("no module compiled, is the file empty?"),
#     }
# }

# execute a given function in the Bench module
def execute(move_vm: MoveVM, fun_name: str):
    # establish running context
    state = EmptyStateView()
    gas_schedule = CostTable.zero()
    data_cache = BlockDataCache.new(state)
    interpreter_context = \
        TransactionExecutionContext.new(GasUnits.new(100_000_000), data_cache)
    metadata = TransactionMetadata.default()

    # module and function to call
    module_id = ModuleId(Address.default(), "Bench")
    move_vm.execute_function(
            module_id,
            fun_name,
            gas_schedule,
            interpreter_context,
            metadata,
            [],
        )


def test_arith():
    bench("arith")

def test_call():
    bench("call")

if str(type(__loader__)).find('pytest') == -1:
    #cProfile.run('bench("arith")', sort='cumtime')
    cProfile.run('bench("call")', sort='cumtime')

