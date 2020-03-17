from libra_vm import *
from libra_vm.runtime.data_cache import RemoteCache, BlockDataCache
from libra_vm.runtime.chain_state import SystemExecutionContext, TransactionExecutionContext
from libra_vm.runtime.code_cache import VMModuleCache
from libra_vm.runtime.loaded_data import FunctionRef, FunctionReference, LoadedModule
from bytecode_verifier import VerifiedModule, VerifiedScript
#use compiler.Compiler
from libra_storage.state_view import StateView
from libra.access_path import AccessPath
from libra.account_address import Address
from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus, StatusType

from libra_vm.file_format import *
from libra_vm.file_format_common import Opcodes, SerializedType, SerializedNativeStructFlag
from libra_vm.gas_schedule import GasAlgebra, GasUnits
from move_vm.types.loaded_data import StructDef, Type
from typing import List, Optional, Mapping
from libra_vm import signature_token_help
from dataclasses import dataclass, field
from libra.rustlib import *
import pytest
import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname

def ident(s):
    return s

class NullStateView(StateView):

    def get(self, _ap: AccessPath) -> Optional[bytes]:
        Err(format_err("no get on null state view"))


    def multi_get(self, _ap: [AccessPath]) -> List[Optional[bytes]]:
        Err(format_err("no get on null state view"))


    def is_genesis(self) -> bool:
        return False


@dataclass
class FakeDataCache(RemoteCache):
    data: Mapping[AccessPath, bytes] = field(default_factory=dict)


    def get0(self, ap: AccessPath) -> Optional[bytes]:
        if ap in self.data:
            return self.data[ap]
        return None


    def set(self, module: CompiledModule):
        ap = AccessPath.code_access_path(module.self_id())
        blob = module.serialize()
        self.data[ap] = blob


    def get(self, access_path: AccessPath) -> Optional[bytes]:
        return self.get0(access_path)



def gen_test_module(name) -> VerifiedModule:
    compiled_module = CompiledModuleMut(
        module_handles = [ModuleHandle(
            name = IdentifierIndex.new(0),
            address = AddressPoolIndex.new(0),
        )],
        struct_handles = [],
        function_handles = [
            FunctionHandle(
                module = ModuleHandleIndex.new(0),
                name = IdentifierIndex.new(1),
                signature = FunctionSignatureIndex.new(0),
            ),
            FunctionHandle(
                module = ModuleHandleIndex.new(0),
                name = IdentifierIndex.new(2),
                signature = FunctionSignatureIndex.new(1),
            ),
        ],

        struct_defs = [],
        field_defs = [],
        function_defs = [
            FunctionDefinition(
                function = FunctionHandleIndex.new(0),
                flags = CodeUnit.PUBLIC,
                acquires_global_resources = [],
                code = CodeUnit(
                    max_stack_size = 10,
                    locals = LocalsSignatureIndex.new(0),
                    code = [Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)],
                ),
            ),
            FunctionDefinition(
                function = FunctionHandleIndex.new(1),
                flags = CodeUnit.PUBLIC,
                acquires_global_resources = [],
                code = CodeUnit(
                    max_stack_size = 10,
                    locals = LocalsSignatureIndex.new(1),
                    code = [Bytecode(Opcodes.RET)],
                ),
            ),
        ],
        type_signatures = [],
        function_signatures = [
            FunctionSignature(
                return_types = [],
                arg_types = [],
                type_formals = [],
            ),
            FunctionSignature(
                return_types = [],
                arg_types = [signature_token_help.U64],
                type_formals = [],
            ),
        ],
        locals_signatures = [
            LocalsSignature([]),
            LocalsSignature([signature_token_help.U64]),
        ],
        identifiers = [name, "func1", "func2"],
        byte_array_pool = [],
        address_pool = [Address.default()],
    ).freeze()
    return VerifiedModule.new(compiled_module)


def gen_test_script() -> VerifiedScript:
    compiled_script = CompiledScriptMut(
        main = FunctionDefinition(
            function = FunctionHandleIndex.new(0),
            flags = CodeUnit.PUBLIC,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 10,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        ),
        module_handles = [
            ModuleHandle(
                address = AddressPoolIndex.new(0),
                name = IdentifierIndex.new(0),
            ),
            ModuleHandle(
                address = AddressPoolIndex.new(0),
                name = IdentifierIndex.new(1),
            ),
        ],
        struct_handles = [],
        function_handles = [
            FunctionHandle(
                name = IdentifierIndex.new(4),
                signature = FunctionSignatureIndex.new(0),
                module = ModuleHandleIndex.new(0),
            ),
            FunctionHandle(
                name = IdentifierIndex.new(2),
                signature = FunctionSignatureIndex.new(0),
                module = ModuleHandleIndex.new(1),
            ),
            FunctionHandle(
                name = IdentifierIndex.new(3),
                signature = FunctionSignatureIndex.new(1),
                module = ModuleHandleIndex.new(1),
            ),
        ],
        type_signatures = [],
        function_signatures = [
            FunctionSignature(
                return_types = [],
                arg_types = [],
                type_formals = [],
            ),
            FunctionSignature(
                return_types = [],
                arg_types = [signature_token_help.U64],
                type_formals = [],
            ),
        ],
        locals_signatures = [LocalsSignature([])],
        identifiers = ["hello", "module", "func1", "func2", "main"],
        byte_array_pool = [],
        address_pool = [Address.default()],
    ).freeze()
    return VerifiedScript.new(compiled_script)



def test_loader_one_module():
    # This test tests the linking of function within a single module = We have a module that defines
    # two functions, each with different name and signature. This test will make sure that we
    # link the function handle with the right function definition within the same module.
    module = gen_test_module("module")
    mod_id = module.self_id()

    data_cache = FakeDataCache()
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    loaded_program = VMModuleCache()
    loaded_program.cache_module(module)
    module_ref = loaded_program.get_loaded_module(mod_id, ctx)

    # Get the function reference of the first two function handles.
    func1_ref = loaded_program\
        .resolve_function_ref(module_ref, FunctionHandleIndex.new(0), ctx)

    func2_ref = loaded_program\
        .resolve_function_ref(module_ref, FunctionHandleIndex.new(1), ctx)


    # The two references should refer to the same module
    assert_equal(
        func2_ref.module(),
        func1_ref.module()
    )

    assert_equal(func1_ref.arg_count(), 0)
    assert_equal(func1_ref.return_count(), 0)
    assert_equal(
        func1_ref.code_definition(),
        [Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)]
    )

    assert_equal(func2_ref.arg_count(), 1)
    assert_equal(func2_ref.return_count(), 0)
    assert_equal(func2_ref.code_definition(), [Bytecode(Opcodes.RET)])



def test_loader_cross_modules():
    script = gen_test_script()
    module = gen_test_module("module")

    loaded_program = VMModuleCache()
    loaded_program.cache_module(module)

    data_cache = FakeDataCache()
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    owned_entry_module = script.into_module()
    loaded_main = LoadedModule.new(owned_entry_module)
    entry_func = FunctionRef.new(loaded_main, CompiledScript.MAIN_INDEX)
    entry_module = entry_func.module()
    func1 = loaded_program\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(1), ctx)

    func2 = loaded_program\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(2), ctx)

    assert_equal(
        func2.module(),
        func1.module()
    )

    assert_equal(func1.arg_count(), 0)
    assert_equal(func1.return_count(), 0)
    assert_equal(
        func1.code_definition(),
        [Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)]
    )

    assert_equal(func2.arg_count(), 1)
    assert_equal(func2.return_count(), 0)
    assert_equal(func2.code_definition(), [Bytecode(Opcodes.RET)])



def test_cache_with_storage():
    owned_entry_module = gen_test_script().into_module()
    loaded_main = LoadedModule.new(owned_entry_module)
    entry_func = FunctionRef.new(loaded_main, CompiledScript.MAIN_INDEX)
    entry_module = entry_func.module()
    print(f"MODULE = {entry_module.as_module()}")

    vm_cache = VMModuleCache()
    data_cache = FakeDataCache()
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    # Function is not defined locally.
    with pytest.raises(VMException) as excinfo:
        vm_cache.resolve_function_ref(entry_module, FunctionHandleIndex.new(1), ctx)

    data_cache = FakeDataCache()
    data_cache.set(gen_test_module("module").into_inner())
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    # Make sure the block cache fetches the code from the view.
    func1 = vm_cache\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(1), ctx)

    func2 = vm_cache\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(2), ctx)


    assert_equal(
        func2.module(),
        func1.module()
    )

    assert_equal(func1.arg_count(), 0)
    assert_equal(func1.return_count(), 0)
    assert_equal(
        func1.code_definition(),
        [Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)]
    )

    assert_equal(func2.arg_count(), 1)
    assert_equal(func2.return_count(), 0)
    assert_equal(func2.code_definition(), [Bytecode(Opcodes.RET)])

    # Clean the fetcher so that there's nothing in the fetcher.
    data_cache = FakeDataCache()
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    func1 = vm_cache\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(1), ctx)

    func2 = vm_cache\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(2), ctx)


    assert_equal(
        func2.module(),
        func1.module()
    )

    assert_equal(func1.arg_count(), 0)
    assert_equal(func1.return_count(), 0)
    assert_equal(
        func1.code_definition(),
        [Bytecode(Opcodes.LD_TRUE), Bytecode(Opcodes.POP), Bytecode(Opcodes.RET)]
    )

    assert_equal(func2.arg_count(), 1)
    assert_equal(func2.return_count(), 0)
    assert_equal(func2.code_definition(), [Bytecode(Opcodes.RET)])



def test_multi_level_cache_write_back():
    vm_cache = VMModuleCache()

    # Put an existing module in the cache.
    module = gen_test_module("existing_module")
    vm_cache.cache_module(module)

    # Create a new script that refers to both published and unpublished modules.
    script = CompiledScriptMut(
        main = FunctionDefinition(
            function = FunctionHandleIndex.new(0),
            flags = CodeUnit.PUBLIC,
            acquires_global_resources = [],
            code = CodeUnit(
                max_stack_size = 10,
                locals = LocalsSignatureIndex(0),
                code = [Bytecode(Opcodes.RET)],
            ),
        ),
        module_handles = [
            # Self
            ModuleHandle(
                address = AddressPoolIndex.new(0),
                name = IdentifierIndex.new(0),
            ),
            # To-be-published Module
            ModuleHandle(
                address = AddressPoolIndex.new(0),
                name = IdentifierIndex.new(1),
            ),
            # Existing module on chain
            ModuleHandle(
                address = AddressPoolIndex.new(0),
                name = IdentifierIndex.new(2),
            ),
        ],
        struct_handles = [],
        function_handles = [
            # main
            FunctionHandle(
                name = IdentifierIndex.new(5),
                signature = FunctionSignatureIndex.new(0),
                module = ModuleHandleIndex.new(0),
            ),
            # Func2 defined in the new module
            FunctionHandle(
                name = IdentifierIndex.new(4),
                signature = FunctionSignatureIndex.new(0),
                module = ModuleHandleIndex.new(1),
            ),
            # Func1 defined in the old module
            FunctionHandle(
                name = IdentifierIndex.new(3),
                signature = FunctionSignatureIndex.new(1),
                module = ModuleHandleIndex.new(2),
            ),
        ],
        type_signatures = [],
        function_signatures = [
            FunctionSignature(
                return_types = [],
                arg_types = [],
                type_formals = [],
            ),
            FunctionSignature(
                return_types = [],
                arg_types = [signature_token_help.U64],
                type_formals = [],
            ),
        ],
        locals_signatures = [LocalsSignature([])],
        identifiers = [
            "hello",
            "module",
            "existing_module",
            "func1",
            "func2",
            "main",
        ],
        byte_array_pool = [],
        address_pool = [Address.default()],
    ).freeze()
    script = VerifiedScript.new(script)

    owned_entry_module = script.into_module()
    loaded_main = LoadedModule.new(owned_entry_module)
    entry_func = FunctionRef.new(loaded_main, CompiledScript.MAIN_INDEX)
    entry_module = entry_func.module()

    vm_cache.cache_module(gen_test_module("module"))

    # After reclaiming we should see it from the cache
    data_cache = FakeDataCache()
    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))
    func2_ref = vm_cache\
        .resolve_function_ref(entry_module, FunctionHandleIndex.new(1), ctx)

    assert_equal(func2_ref.arg_count(), 1)
    assert_equal(func2_ref.return_count(), 0)
    assert_equal(func2_ref.code_definition(), [Bytecode(Opcodes.RET)])


#cargo run -p compiler -- --no-stdlib -m ../libra-vm/test/vm_runtime/code1/*.mvir
def decompile_modules(name) -> List[CompiledModule]:
    curdir = dirname(__file__)
    sdir = join(curdir, name)
    mvs = [f for f in listdir(sdir) if f.endswith(".mv")]
    ret = []
    for mv in mvs:
        filename = abspath(join(sdir, mv))
        with open(filename, 'r') as file:
            amap = json.load(file)
            code = bytes(amap['code'])
            obj = CompiledModule.deserialize(code)
            ret.append(obj)
    return ret



def parse_and_compile_modules(s) -> List[CompiledModule]:
    return []
#     compiler = Compiler {
#         skip_stdlib_deps = True,
#         ..Compiler.default()
#     }
#     compiler
#         .into_compiled_program(s)
#         .expect("Failed to compile program")
#         .modules
# }


def test_same_module_struct_resolution():
    vm_cache = VMModuleCache()
    data_cache = FakeDataCache()
    modules = decompile_modules("code1")
    for module in modules:
        data_cache.set(module)

    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    module_id = ModuleId(Address.default(), "M1")
    module_ref = vm_cache.get_loaded_module(module_id, ctx)

    block_data_cache = BlockDataCache.new(NullStateView)
    context = TransactionExecutionContext.new(GasUnits.new(100_000_000), block_data_cache)
    struct_x = vm_cache\
        .resolve_struct_def(module_ref, StructDefinitionIndex.new(0), context)

    struct_t = vm_cache\
        .resolve_struct_def(module_ref, StructDefinitionIndex.new(1), context)

    assert_equal(struct_x, StructDef.new([Type('Bool')]))
    assert_equal(
        struct_t,
        StructDef.new([
            Type('U64'),
            Type('Struct', StructDef.new([Type('Bool')]))
        ]),
    )



def test_multi_module_struct_resolution():
    vm_cache = VMModuleCache()
    data_cache = FakeDataCache()
    modules = decompile_modules("code2")
    for module in modules:
        data_cache.set(module)

    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    # load both modules in the cache
    module_id_1 = ModuleId(Address.default(), "M1")
    vm_cache.get_loaded_module(module_id_1, ctx)
    module_id_2 = ModuleId(Address.default(), "M2")
    module2_ref = vm_cache.get_loaded_module(module_id_2, ctx)

    block_data_cache = BlockDataCache.new(NullStateView)
    context = TransactionExecutionContext.new(GasUnits.new(100_000_000), block_data_cache)

    struct_t = vm_cache\
        .resolve_struct_def(module2_ref, StructDefinitionIndex.new(0), context)

    assert_equal(
        struct_t,
        StructDef.new([
            Type('U64'),
            Type('Struct', StructDef.new([Type('Bool')]))
        ]),
    )



def test_field_offset_resolution():
    vm_cache = VMModuleCache()
    data_cache = FakeDataCache()
    modules = decompile_modules("code3")
    for module in modules:
        data_cache.set(module)

    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    module_id = ModuleId(Address.default(), ident("M1"))
    module_ref = vm_cache.get_loaded_module(module_id, ctx)

    f_idx = module_ref.field_defs_table.get(ident("f"))
    assert_equal(module_ref.get_field_offset(f_idx), 0)

    g_idx = module_ref.field_defs_table.get(ident("g"))
    assert_equal(module_ref.get_field_offset(g_idx), 1)

    i_idx = module_ref.field_defs_table.get(ident("i"))
    assert_equal(module_ref.get_field_offset(i_idx), 0)

    x_idx = module_ref.field_defs_table.get(ident("x"))
    assert_equal(module_ref.get_field_offset(x_idx), 1)

    y_idx = module_ref.field_defs_table.get(ident("y"))
    assert_equal(module_ref.get_field_offset(y_idx), 2)


def test_dependency_fails_verification():
    vm_cache = VMModuleCache()

    # This module has a class inside a resource, which should fail verification. But assume that
    # it made its way onto the chain somehow (e.g. there was a bug in an older version of the
    # bytecode verifier).

    data_cache = FakeDataCache()
    modules = decompile_modules("code4")
    for module in modules:
        data_cache.set(module)

    ctx = SystemExecutionContext.new(data_cache, GasUnits.new(0))

    module_id = ModuleId(Address.default(), ident("Test"))

    with pytest.raises(VMException) as excinfo:
        vm_cache.get_loaded_module(module_id, ctx)

    errors = excinfo.value.vm_status
    assert (errors[0].status_type() == StatusType.Verification)
    assert (errors[0].major_status == StatusCode.INVALID_RESOURCE_FIELD)
