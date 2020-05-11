from enum import IntEnum
from typing import Callable, Union, Any, Tuple, Optional, Set
from mol.compiler.bytecode_source_map.source_map import FunctionSourceMap
from mol.global_source_mapping import GlobalSourceMapping
from mol.move_core import JsonPrintable
import logging

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

    def trace_call(self):
        TracableFrame.CURRENT_FRAME = self
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            self.try_attach_mapping()
            ltrace = gtrace(self, TraceType.CALL, None)
            if ltrace is not None:
                if isinstance(ltrace, tuple):
                    line_trace, opcode_trace = ltrace
                    self.f_trace = line_trace
                    self.f_trace_opcodes = opcode_trace
                else:
                    self.f_trace = ltrace

    def trace_return(self):
        gtrace = GlobalTracer.gettrace()
        if gtrace is not None:
            gtrace(self, TraceType.RETURN, None)

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
            return self.function_map().get_code_location(0).line_no
        else:
            return None

    def executable_linenos(self) -> Set[int]:
        if self.mapping is not None:
            return self.function_map().executable_linenos()
        else:
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
