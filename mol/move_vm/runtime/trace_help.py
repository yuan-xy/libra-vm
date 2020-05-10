from enum import IntEnum
from typing import Callable, Union, Any, Tuple, Optional, Set
from mol.compiler.bytecode_source_map.source_map import FunctionSourceMap
from mol.global_source_mapping import GlobalSourceMapping
from mol.move_core import JsonPrintable


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
        CURRENT_FRAME = self
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

    def function_map(self) -> Optional[FunctionSourceMap]:
        if self.mapping is not None:
            return self.mapping.source_map.function_map[self.function.idx.v0]
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
