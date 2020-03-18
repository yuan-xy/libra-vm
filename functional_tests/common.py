from __future__ import annotations
from dataclasses import dataclass
from libra.rustlib import usize
from typing import Any, List, Optional

# Wrapper of an inner object with start and end source locations.
@dataclass
class Sp:
    inner: Any
    start: usize
    end: usize


    def into_inner(self) -> Any:
        return self.inner


    def as_inner(self) -> Any:
        return self.inner


    def map(self, f: Callable) -> Sp:
        return Sp(
            inner= f(self.inner),
            start= self.start,
            end= self.end,
        )


    def into_line_sp(self, line: usize) -> LineSp:
        return LineSp(
            self.inner,
            line,
            self.start,
            self.end,
        )


    def as_ref(self) -> Any:
        return self.as_inner()



# Wrapper of an inner object with line, start and end source locations.
@dataclass
class LineSp:
    inner: Any
    line: usize
    start: usize
    end: usize


    def into_inner(self) -> Any:
        return self.inner


    def as_inner(self) -> Any:
        return self.inner


    def map(self, f: Callable) -> LineSp:
        return LineSp(
            inner= f(self.inner),
            line= self.line,
            start= self.start,
            end= self.end,
        )


    def as_ref(self) -> Any:
        return self.as_inner()



# Checks if `s` starts with `prefix`. If yes, returns a reference to the remaining part
# with the prefix stripped away.
def strip(s: str, prefix: str) -> Optional[str]:
    if s.startswith(prefix):
        return s[prefix.__len__():]
    else:
        return None
