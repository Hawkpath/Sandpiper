from decimal import Decimal as D
import re
from typing import Optional, Tuple

from bidict import bidict as bidict_base
from pint import UnitRegistry
from pint.quantity import Quantity

__all__ = ['imperial_metric', 'quantity_pattern']

ureg = UnitRegistry(
    autoconvert_offset_to_baseunit=True,  # For temperatures
    non_int_type=D
)
ureg.define('@alias degreeC = c = C = degreec = degc = degC')
ureg.define('@alias degreeF = f = F = degreef = degf = degF')
Q_ = ureg.Quantity


# noinspection PyPep8Naming
class bidict(bidict_base):

    def __contains__(self, item):
        return (super(bidict, self).__contains__(item)
                or super(bidict, self.inverse).__contains__(item))

    # noinspection PyArgumentList
    def __getitem__(self, item):
        try:
            return super(bidict, self).__getitem__(item)
        except KeyError:
            return super(bidict, self.inverse).__getitem__(item)


unit_map = bidict({
    # Length
    ureg.km: ureg.mile,
    ureg.meter: ureg.foot,
    ureg.cm: ureg.inch,
    # Mass
    ureg.kilogram: ureg.pound,
    # Temperature
    ureg['°C'].u: ureg['°F'].u
})

quantity_pattern = re.compile(r'{(.+?)}')
imperial_height_pattern = re.compile(
    r'^(?=.)(?:(?P<foot>[\d]+)\')?(?:(?(foot) |)(?P<inch>[\d.]+)\")?$')


def imperial_metric(quantity_str: str) -> Optional[Tuple[Quantity, Quantity]]:
    """
    Parse and convert a quantity string between imperial and metric

    :param quantity_str: a string that may contain a quantity to be
        converted
    :return: ``None`` if the string was not a known or supported quantity,
        otherwise a tuple of original quantity and converted quantity
    """

    if height := imperial_height_pattern.match(quantity_str):
        # Added support for imperial shorthand units for length
        # e.g. 5' 8" == 5 feet + 8 inches
        foot = Q_(D(foot), 'foot') if (foot := height.group('foot')) else 0
        inch = Q_(D(inch), 'inch') if (inch := height.group('inch')) else 0
        quantity = foot + inch
    else:
        # Regular parsing
        quantity = ureg.parse_expression(quantity_str)

    if not isinstance(quantity, Quantity) or quantity.units not in unit_map:
        # Unrecognized unit
        return None
    conversion_unit = unit_map[quantity.units]

    return quantity, quantity.to(conversion_unit)
