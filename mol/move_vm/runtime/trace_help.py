from enum import IntEnum
from typing import Callable, Union, Any, Tuple
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
	def address_module_function(self) -> Tuple[str, str, str]:
		return self.module().address().hex(), self.module().name(), self.function.name()

	def try_attach_mapping(self) -> None:
		a, m, f = self.address_module_function()
		mapping = GlobalSourceMapping.find(a, m, f)
		if mapping is not None and mapping.has_source_code_and_map():
			self.mapping = mapping
		else:
			self.mapping = None


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
