from abc import ABCMeta, abstractmethod
from typing import *


class ConfigConverterBase(metaclass=ABCMeta):

    @abstractmethod
    def convert(self, value: Any) -> Any:
        pass

    @classmethod
    def _check_tuple(
            cls, tuple_: Tuple, *field_names: str
    ) -> Tuple:
        if len(tuple_) != len(field_names):
            raise ValueError(
                f"Missing type arguments. Expected "
                f"{cls.__name__}[{', '.join(field_names)}]"
            )
        return tuple_

    @staticmethod
    def _typecheck(
            type_: Union[Type, Tuple[Type, ...]], value: Any, name: str
    ) -> NoReturn:
        if not isinstance(value, type_):
            raise TypeError(
                f"{name}={value} must be "
                f"{'one ' if isinstance(type_, tuple) else ''}"
                f"of type {type_}, not {type(value)}"
            )


V_Base = TypeVar('V_Base')
V_Target = TypeVar('V_Target')


class Convert(ConfigConverterBase):

    def __init__(self, base_type: Type[V_Base], target_type: Type[V_Target]):
        self._typecheck(type, base_type, 'base_type')
        self._typecheck(type, target_type, 'target_type')
        self.base_type = base_type
        self.target_type = target_type

    def __class_getitem__(
            cls, base_and_target_types: Tuple[Type[V_Base], Type[V_Target]]
    ):
        base_type, target_type = cls._check_tuple(
            base_and_target_types, 'base_type', 'target_type'
        )
        return cls(base_type, target_type)

    def convert(self, value: V_Base) -> V_Target:
        if not isinstance(value, self.base_type):
            raise TypeError(f'Expected type {self.base_type}, got {type(value)}')
        return self.target_type(value)


# noinspection PyMissingConstructor
class BoundedInt(int, ConfigConverterBase):

    def __init__(self, min: Optional[int], max: Optional[int]):
        self._typecheck((int, type(None)), min, 'min')
        self._typecheck((int, type(None)), max, 'max')
        self.min = min
        self.max = max

    def __class_getitem__(cls, min_max: Tuple[Optional[int], Optional[int]]):
        cls._check_tuple(min_max, 'min', 'max')
        return cls(min=min_max[0], max=min_max[1])

    def convert(self, value: Any) -> int:
        self._typecheck(int, value, 'value')
        if self.min is not None and value < self.min:
            raise ValueError(f"Value must be greater than or equal to {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"Value must be less than or equal to {self.max}")
        return value


