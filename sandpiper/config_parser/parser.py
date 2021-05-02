import json
from typing import *
from typing import TextIO

from .converters import ConfigConverterBase
from .exceptions import *
from .misc import *

__all__ = ('ConfigCompound',)

NoDefault = object()


def is_json_type(value: Any) -> bool:
    return value in (list, str, int, float, True, False, None)


class ConfigCompound:

    __path: str

    def __init__(self, config: Union[dict, str, TextIO], *, _compound_path=''):
        self.__path = _compound_path
        self.__parse(config)

    def __parse(self, config: Union[dict, str, TextIO]):
        if isinstance(config, str):
            json_parsed = json.loads(config)
        elif isinstance(config, TextIO):
            json_parsed = json.load(config)
        else:
            raise TypeError(
                f"config must be one of (TextIO, str), got {type(config)}"
            )

        # Iterate through __dict__ to get fields with default values
        encountered = set()
        for field_name, default in self.__dict__.items():
            encountered.add(field_name)
            if field_name.startswith('_'):
                continue
            field_type = type(default)
            self.__read_field(json_parsed, field_name, field_type)

        # Iterate through __annotations__ to get the remaining fields with
        # type annotations
        for field_name, field_type in self.__annotations__.items():
            if field_name in encountered or field_name.startswith('_'):
                continue
            self.__read_field(json_parsed, field_name, field_type)

    def __read_field(
            self, json_parsed: Dict[str, Any], field_name: str,
            field_type: Any, default: Any = NoDefault
    ):
        qualified_name = qualified(self.__path, field_name)
        if (isinstance(field_type, type)
                and issubclass(field_type, ConfigCompound)):
            assert default is NoDefault, (
                f"Config field {qualified_name} is annotated as a compound "
                f"and should not have a default value"
            )
            # The type is a compound tag, so pass the json-parsed dict into
            # the compound type for further parsing
            final_value = field_type(
                json_parsed.get(field_name, {}),
                _compound_path=f"{self.__path}.{field_name}"
            )
            setattr(self, field_name, final_value)
            return

        try:
            value = json_parsed[field_name]
        except KeyError:
            if default is NoDefault:
                raise MissingFieldError(qualified_name)
            final_value = default
        else:
            # No default was used
            try:
                final_value = _convert(value, field_type, qualified_name)
            except ParsingError as e:
                raise e

        setattr(self, field_name, final_value)


def _convert(
        value: Any, type_: Any, qualified_name: str
):
    if type_ is Any:
        # Any type is accepted
        return value

    if isinstance(type_, ConfigConverterBase):
        # Use a converter
        return type_.convert(value)

    if hasattr(type_, '__origin__') and hasattr(type_, '__args__'):
        # Use special rules for typing module types
        type_origin = type_.__origin__
        type_args = type_.__args__

        if type_origin is Union:
            # The subtypes in a union might be other special typing types.
            # Recursively call this function with each subtype
            for subtype in type_args:
                try:
                    return _convert(value, subtype, qualified_name)
                except ConfigSchemaError as e:
                    # If we get this error, something is wrong with the schema,
                    # not the config value
                    raise e
                except Exception:
                    # This is normal, ideally this will happen for all but
                    # one matching subtype
                    pass
            raise ValueError(
                f"Value at {qualified_name} didn't match any type in {type_}"
            )

        if type_origin is tuple:
            # Convert every value in the tuple
            typecheck(list, **{qualified_name: value})
            converted_list = []
            if len(value) != len(type_args):
                raise ValueError(
                    f"Expected a tuple of length {len(type_args)}, got "
                    f"{len(value)}"
                )
            for i, subtype in enumerate(type_args):
                converted = _convert(
                    value[i], subtype, f"{qualified_name}[{i}]"
                )
                converted_list.append(converted)
            return tuple(converted_list)

        if type_origin is list:
            # Convert every value in the tuple
            typecheck(list, **{qualified_name: value})
            list_type = type_args[0]
            converted_list = []
            for i, subvalue in enumerate(value):
                converted = _convert(
                    subvalue, list_type, f"{qualified_name}[{i}]"
                )
                converted_list.append(converted)
            return converted_list

        if type_origin is Literal:
            # Check equality with one of the literal values
            if value not in type_args:
                raise ValueError(
                    f"Value must be equal to one of {type_args}"
                )
            return value

        raise ConfigSchemaError(
            f"Special type annotation {type_origin} is not accepted."
        )

    if is_json_type(type_):
        # Simple typecheck
        typecheck(type_, value=value)
        return value

    # Some other annotation we can't handle
    raise ConfigSchemaError(
        f"Type annotation {type(type_)} for {qualified_name} is not "
        f"accepted. Maybe you want to use the converters.Convert "
        f"annotation?"
    )
