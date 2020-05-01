from typing import Any, List, Optional, Mapping

# Parses each line in the given input as `T`.
def parse_each_line_as(s: str, T: Any) -> List[Any]:
    ss = [x.strip() for x in s.splitlines()]
    return [T.from_str(x) for x in ss if x]

