from enum import IntEnum
from typing import Callable, Union, Any
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
	def address_module_function(self):
		return self.module().address().hex(), self.module().name(), self.function.name()


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
