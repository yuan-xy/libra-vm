from enum import IntEnum
from typing import Callable, Union, Any, Tuple, Optional, Set, List
from mol.compiler.bytecode_source_map.source_map import FunctionSourceMap
from mol.global_source_mapping import GlobalSourceMapping
from mol.stdlib import find_stdlib_module_by_name
from mol.move_core import JsonPrintable
import logging
from mol.move_vm.runtime.loaded_data.function import LoadedModule
from libra.account_address import Address

logger = logging.getLogger(__name__)


class TraceType(IntEnum):
    CALL = 0
    EXCEPTION = 1
    LINE = 2
    RETURN = 3
    NATIVE_CALL = 4
    NATIVE_EXCEPTION = 5
    NATIVE_RETURN = 6
    OPCODE = 7


class TracableFrame(JsonPrintable):
    CURRENT_FRAME = None

    def address_module_function(self) -> Tuple[str, str, str]:
        return self.module().address().hex(), self.module().name(), self.function.name()

    @classmethod
    def break_main(cls, parsed_script):
        """set default breakpoint for script on main function
        """
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            mdb = gtrace.__self__
            func_map = parsed_script.source_map.function_map[0]
            line = func_map.code_map[0].line_no
            file = parsed_script.source_mapping.source_code.path
            mdb.set_break(mdb.canonic(file), line)


    @classmethod
    def trace_reset(cls):
        """Reset debugger every time after run prologue/main/epilogue
        """
        TracableFrame.CURRENT_FRAME = None
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            gtrace.__self__.reset()

    def trace_call(self):
        TracableFrame.CURRENT_FRAME = self
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            self.try_attach_mapping()
            if self.mapping is not None:
                self.line_no = self.function_source_map().decl_location.line_no
            ltrace = gtrace(self, TraceType.CALL, None)
            if ltrace is not None:
                if isinstance(ltrace, tuple):
                    line_trace, opcode_trace = ltrace
                    self.f_trace = line_trace
                    self.f_trace_opcodes = opcode_trace
                else:
                    self.f_trace = ltrace

    def trace_return(self, operand_stack):
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            size = self.function.return_count()
            return_value = operand_stack.v0[0-size:]
            gtrace(self, TraceType.RETURN, return_value)

    def try_attach_mapping(self) -> None:
        if self.mapping is not None:
            return
        a, m, f = self.address_module_function()
        mapping = GlobalSourceMapping.find(a, m)
        if mapping is not None and mapping.has_source_code_and_map():
            self.mapping = mapping
        else:
            self.mapping = None

    def source_filename(self) -> Optional[str]:
        if self.mapping is not None:
            return self.mapping.source_code.path
        else:
            return None

    def function_source_map(self) -> Optional[FunctionSourceMap]:
        if self.mapping is not None:
            return self.mapping.source_map.function_map[self.function.idx.v0]
        else:
            return None

    def get_lineno(self, pc) -> int:
        func_map = self.function_source_map()
        if func_map is not None:
            if pc in func_map.code_map:
                return func_map.code_map[pc].line_no
            else:
                logger.error((self.module().name(), self.function.name(), pc))
                # TTODO: why can't find this codeoffset in code_map, inline func or native func?
                # breakpoint()
                return None
        else:
            return None

    def src_line(self) -> str:
        if self.mapping is not None:
            return self.mapping.source_code.lines[self.line_no-1]
        else:
            return None

    def src_lines(self) -> str:
        if self.mapping is not None:
            return self.mapping.source_code.lines
        else:
            return None

    def frame_lines(self) -> str:
        func_map = self.function_source_map()
        if func_map is not None:
            start = func_map.code_map[0].line_no - 1
            end = max(func_map.executable_linenos())
            return self.mapping.source_code.lines[start:end]
        else:
            return None

    def frame_first_lineno(self) -> int:
        func_map = self.function_source_map()
        if func_map is not None:
            return func_map.code_map[0].line_no
        else:
            return None


    def first_lineno(self) -> int:
        if self.mapping is not None:
            return self.function_source_map().get_code_location(0).line_no
        else:
            return None

    def executable_linenos(self) -> Set[int]:
        if self.mapping is not None:
            return self.function_source_map().executable_linenos()
        else:
            return None

    def locals_name_value(self) -> List[str]:
        if self.mapping is not None:
            values = self.locls.into_inner().value
            maps = self.function_source_map().locls
            zipped = zip(maps, values)
            return [(m[0], v.value) for m,v in zipped]
        else:
            return self.locls.to_json_serializable()

    def locals_names(self) -> List[str]:
        if self.mapping is not None:
            return [m[0] for m in self.function_source_map().locls]
        else:
            return []

    def local(self, name):
        if self.mapping is not None:
            values = self.locls.into_inner().value
            maps = self.function_source_map().locls
            zipped = zip(maps, values)
            for m,v in zipped:
                if m[0] == name:
                    return v
        return None




CallbackReturn = Union[None, Callable]
TraceCallback = Callable[[TracableFrame, TraceType, Any], CallbackReturn]

class GlobalTracer:
    tracer: TraceCallback = None

    @classmethod
    def settrace(cls, trace: TraceCallback):
        GlobalTracer.tracer = trace

    @classmethod
    def gettrace(cls) -> TraceCallback:
        return GlobalTracer.tracer

def find_function_map_by_name(name: str) -> Optional[Tuple[FunctionSourceMap, str]]:
    if "::" not in name:
        frame = TracableFrame.CURRENT_FRAME
        func_idx = frame.module().function_defs_table.get(name)
        if func_idx is not None:
            # func = FunctionRef.new(frame.module(), func_idx)
            return frame.mapping.source_map.function_map[func_idx.v0], frame.source_filename()
        else:
            return None
    else:
        mname, fname = name.split("::")
        address = Address.default().hex()
        mapping = GlobalSourceMapping.find_mapping(f"{address}::{mname}")
        module = find_stdlib_module_by_name(mname)
        module = LoadedModule.new(module)
        func_idx = module.function_defs_table.get(fname)
        if func_idx is not None:
            return mapping.source_map.function_map[func_idx.v0], mapping.source_code.path
        else:
            return None
