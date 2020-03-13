from typing import List, Any
from dataclasses import dataclass, field


class ParseError(Exception):
    pass


@dataclass
class ParseErrorInvalidToken(ParseError):
    location: Any

    def __str__(self):
        return f"Invalid token at {self.location}"


@dataclass
class ParseErrorUser(ParseError):
    error: Any


