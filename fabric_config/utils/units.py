"""
Unit conversion for the app menu: "10 km to mi", "72f in c", "=5 GiB to MB".

Each unit is a factor to its dimension's base unit; temperatures are affine and
handled apart. Matching is case-insensitive except where case means something
(MB vs Mb, mm vs Mm aren't both listed, so the lowercased name is enough).
"""

import re

from fabric_config.utils.app_search import calculate

# dimension -> {name: factor to the base unit}
_UNITS: dict[str, dict[str, float]] = {
    "length": {
        "mm": 1e-3, "millimeter": 1e-3, "millimeters": 1e-3,
        "cm": 1e-2, "centimeter": 1e-2, "centimeters": 1e-2,
        "m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0,
        "km": 1e3, "kilometer": 1e3, "kilometers": 1e3,
        "in": 0.0254, "inch": 0.0254, "inches": 0.0254, '"': 0.0254,
        "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "'": 0.3048,
        "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
        "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
        "nmi": 1852.0,
    },
    "mass": {
        "mg": 1e-6, "g": 1e-3, "gram": 1e-3, "grams": 1e-3,
        "kg": 1.0, "kilo": 1.0, "kilos": 1.0, "kilogram": 1.0, "kilograms": 1.0,
        "t": 1e3, "tonne": 1e3, "tonnes": 1e3,
        "oz": 0.028349523125, "ounce": 0.028349523125, "ounces": 0.028349523125,
        "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237,
        "pounds": 0.45359237, "st": 6.35029318, "stone": 6.35029318,
    },
    "volume": {
        "ml": 1e-3, "cl": 1e-2, "dl": 0.1, "l": 1.0, "liter": 1.0, "liters": 1.0,
        "litre": 1.0, "litres": 1.0, "tsp": 0.00492892, "tbsp": 0.0147868,
        "cup": 0.236588, "cups": 0.236588, "floz": 0.0295735,
        "pt": 0.473176, "pint": 0.473176, "pints": 0.473176,
        "qt": 0.946353, "gal": 3.78541, "gallon": 3.78541, "gallons": 3.78541,
    },
    "time": {
        "ms": 1e-3, "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0,
        "seconds": 1.0, "min": 60.0, "mins": 60.0, "minute": 60.0,
        "minutes": 60.0, "h": 3600.0, "hr": 3600.0, "hrs": 3600.0,
        "hour": 3600.0, "hours": 3600.0, "d": 86400.0, "day": 86400.0,
        "days": 86400.0, "wk": 604800.0, "week": 604800.0, "weeks": 604800.0,
        "yr": 31557600.0, "year": 31557600.0, "years": 31557600.0,
    },
    "speed": {
        "m/s": 1.0, "mps": 1.0, "km/h": 1 / 3.6, "kmh": 1 / 3.6, "kph": 1 / 3.6,
        "mph": 0.44704, "kn": 0.514444, "knot": 0.514444, "knots": 0.514444,
    },
    "data": {
        "b": 1 / 8, "bit": 1 / 8, "bits": 1 / 8, "byte": 1.0, "bytes": 1.0,
        "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "pb": 1e15,
        "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40, "pib": 2**50,
        "kbit": 1e3 / 8, "mbit": 1e6 / 8, "gbit": 1e9 / 8,
    },
    "area": {
        "m2": 1.0, "sqm": 1.0, "km2": 1e6, "sqkm": 1e6, "ha": 1e4,
        "hectare": 1e4, "hectares": 1e4, "acre": 4046.8564224,
        "acres": 4046.8564224, "ft2": 0.09290304, "sqft": 0.09290304,
        "mi2": 2589988.110336, "sqmi": 2589988.110336,
    },
}  # fmt: skip

_TEMPERATURES = {
    "c": "C", "°c": "C", "celsius": "C",
    "f": "F", "°f": "F", "fahrenheit": "F",
    "k": "K", "kelvin": "K",
}  # fmt: skip

# names whose case matters: B(yte) vs b(it), and the bit rates
_CASED = {"B": ("data", 1.0), "Mb": ("data", 1e6 / 8), "Gb": ("data", 1e9 / 8)}

_PATTERN = re.compile(
    r"^\s*(?P<value>.+?)\s*(?P<src>[A-Za-z°'\"][A-Za-z°/'\"²0-9]*)\s+"
    r"(?:to|in|as|->)\s+(?P<dst>[A-Za-z°/'\"²0-9]+)\s*$"
)


def _lookup(name: str) -> tuple[str, float] | None:
    if name in _CASED:
        return _CASED[name]
    lower = name.lower().replace("²", "2")
    for dimension, units in _UNITS.items():
        if lower in units:
            return dimension, units[lower]
    return None


def _to_kelvin(value: float, scale: str) -> float:
    return {"C": value + 273.15, "F": (value - 32) * 5 / 9 + 273.15, "K": value}[scale]


def _from_kelvin(value: float, scale: str) -> float:
    return {"C": value - 273.15, "F": (value - 273.15) * 9 / 5 + 32, "K": value}[scale]


def _format(value: float) -> str:
    if value != 0 and (abs(value) >= 1e12 or abs(value) < 1e-4):
        return f"{value:.6g}"
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def convert(query: str) -> str | None:
    """ "10 km to mi" -> "6.213712 mi", or None if `query` isn't a conversion."""
    match = _PATTERN.match(query)
    if not match:
        return None
    number = calculate(match["value"])
    if number is None:
        return None
    try:
        value = float(number)
    except ValueError:
        return None
    src, dst = match["src"], match["dst"]

    src_temp = _TEMPERATURES.get(src.lower())
    dst_temp = _TEMPERATURES.get(dst.lower())
    if src_temp and dst_temp:
        result = _from_kelvin(_to_kelvin(value, src_temp), dst_temp)
        return (
            f"{_format(result)} °{dst_temp}"
            if dst_temp != "K"
            else f"{_format(result)} K"
        )

    src_unit, dst_unit = _lookup(src), _lookup(dst)
    if not src_unit or not dst_unit or src_unit[0] != dst_unit[0]:
        return None
    return f"{_format(value * src_unit[1] / dst_unit[1])} {dst}"
