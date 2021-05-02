from typing import *

from .misc import qualified

__all__ = (
    'ConfigSchemaError', 'ConfigParsingError', 'MissingFieldError',
    'ParsingError'
)


class ConfigSchemaError(Exception):
    pass


class ConfigParsingError(Exception):
    pass


class MissingFieldError(ConfigParsingError):

    def __init__(self, qualified_name: str):
        self.qualified_name = qualified_name

    def __str__(self):
        return f"Missing required field {self.qualified_name}"


class ParsingError(ConfigParsingError):

    def __init__(
            self, value: Any, target_type: Type, base_exc: Exception,
            qualified_name: str = ''
    ):
        self.value = value
        self.target_type = target_type
        self.base_exc = base_exc
        self.qualified_name = qualified_name

    def __str__(self):
        return (
            f"Failed to parse config value ("
            f"qualified_name={self.qualified_name} value={self.value!r} "
            f"target_type={self.target_type} exc=\"{self.base_exc}\""
            f")"
        )
