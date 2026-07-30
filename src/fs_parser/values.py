import json
import logging
import re
from math import acos, asin, atan, cos, pi, sin, sqrt, tan  # noqa: F401

logger = logging.getLogger(__name__)

# Default tolerance for long_round when a caller does not pass one explicitly.
# Override globally via set_default_tolerance() (e.g. scripts/parse_fscode.py --tolerance).
DEFAULT_TOLERANCE = 1e-10


def set_default_tolerance(tolerance: float) -> None:
    """Set the global long_round tolerance used when no explicit tolerance is given."""
    global DEFAULT_TOLERANCE
    DEFAULT_TOLERANCE = tolerance


def parse_json_line(line: str) -> dict:
    """Parse the JSON object embedded in a line, with fallbacks for escaping quirks."""
    # Extract the object part (between { and })
    match = re.search(r'\{(.+)\}', line)
    if not match:
        return {}
    # build JSON string
    object_content = match.group(1)
    json_string = '{' + object_content + '}'
    json_string = json_string.rstrip(';').strip()

    try:
        parsed = json.loads(json_string)
        return parsed
    except Exception as e:
        logger.debug(f'JSON parsing failed: {e}')

    try:
        parsed = json.loads(json_string.encode('raw_unicode_escape').decode('utf-8'))
        logger.debug(f'Workaround 1: {parsed}')
        return parsed
    except Exception:
        pass

    try:
        parsed = json.loads(json_string.replace('\\', ''))
        logger.debug(f'Workaround 2: {parsed}')
        return parsed
    except Exception:
        pass

    try:
        json_string = re.sub(r'("text"\s*:\s*)"(?:[^"\\]|\\.)*"', r'\1"none"', json_string)
        parsed = json.loads(json_string)
        logger.debug(f'Workaround 3: {parsed}')
        return parsed
    except Exception:
        raise


def long_round(number: float, max_decimals: int = 6, tolerance: float | None = None) -> float | int:
    """
    Smart rounding that tries different decimal places and picks the simplest
    representation that's close enough to the original.

    ``tolerance`` defaults to the module-level DEFAULT_TOLERANCE when not supplied.
    """
    if tolerance is None:
        tolerance = DEFAULT_TOLERANCE

    def check_zero(num):
        return int(num) if str(num)[-2:] == '.0' else num

    if number == 0:
        return 0

    # Try rounding to different decimal places
    for decimals in range(max_decimals + 1):
        rounded = round(number, decimals)
        if abs(number - rounded) < tolerance:
            return check_zero(rounded)

    # If no good rounding found, return original
    return check_zero(number)


def clean_try_expression(value: str) -> str:
    """Normalise a parameter value: unwrap try(...)/.value, convert units to mm, round."""
    value_stripped = value.strip()

    if value_stripped.startswith('[') or (value_stripped.startswith('{') and not value_stripped.endswith('.value')):
        value = convert_to_millimeters(value)
        value = value.replace('millimeter', 'mm')
        return round_numbers_in_value(value)

    if '.value' in value and value.startswith('{') and value.endswith('.value'):
        value_match = re.search(r"'value'\s*:\s*(.*?)(?:,\s*'|\s*})", value)
        if value_match:
            value = value_match.group(1).strip()
        else:
            value_match = re.search(r'"value"\s*:\s*(.*?)(?:,\s*"|\s*})', value)
            if value_match:
                value = value_match.group(1).strip()
    elif '.value' in value:
        value = re.sub(r'\s*\}\s*\.value\s*', '}', value)

    if 'roundWithinTolerance(' in value:
        round_start = value.find('roundWithinTolerance(')
        if round_start != -1:
            bracket_start = round_start + len('roundWithinTolerance(')
            bracket_count = 1
            bracket_end = bracket_start

            while bracket_end < len(value) and bracket_count > 0:
                if value[bracket_end] == '(':
                    bracket_count += 1
                elif value[bracket_end] == ')':
                    bracket_count -= 1
                bracket_end += 1

            if bracket_count == 0:
                inner_content = value[bracket_start : bracket_end - 1]
                value = value[:round_start] + inner_content + value[bracket_end:]

    if 'try(' in value:
        try_start = value.find('try(')
        if try_start != -1:
            bracket_start = try_start + 4
            bracket_count = 1
            bracket_end = bracket_start

            while bracket_end < len(value) and bracket_count > 0:
                if value[bracket_end] == '(':
                    bracket_count += 1
                elif value[bracket_end] == ')':
                    bracket_count -= 1
                bracket_end += 1

            if bracket_count == 0:
                cleaned = value[bracket_start : bracket_end - 1]
                cleaned = convert_to_millimeters(cleaned)
                cleaned = cleaned.replace('millimeter', 'mm')
                return round_numbers_in_value(cleaned)

    value = convert_to_millimeters(value)
    value = value.replace('millimeter', 'mm')
    return round_numbers_in_value(value)


def round_numbers_in_value(value_str: str) -> str:
    """Apply long_round to every numeric literal in the string."""

    def replace_number(match):
        number = float(match.group(0))
        rounded = long_round(number)
        if rounded == int(rounded):
            return str(int(rounded))
        else:
            return str(rounded)

    number_pattern = r'-?\d+\.?\d*'
    return re.sub(number_pattern, replace_number, value_str)


def convert_to_millimeters(value_str: str) -> str:
    """Convert inch/foot/centimeter/meter unit expressions in the string to millimetres."""
    conversion_factors = {'inch': 25.4, 'foot': 304.8, 'centimeter': 10.0, 'meter': 1000.0}

    bracket_pattern = r'(\([^)]+\))\s*\*\s*(inch|foot|centimeter|meter|degree)\b'

    pattern = r'(-?(?:\d*\.\d+|\d+(?:\.\d+)?))\s*\*\s*(inch|foot|centimeter|meter)\b'

    def replace_bracket_unit(match):
        expression = match.group(1)
        unit = match.group(2)
        try:
            replacement = f'{eval(expression[1:-1])} * {unit}'
        except SyntaxError:
            replacement = match.group(0)
        return replacement

    def replace_unit(match):
        number_str = match.group(1)
        unit = match.group(2)

        if number_str.startswith('.'):
            number_str = '0' + number_str
        elif number_str.startswith('-.'):
            number_str = '-0' + number_str[1:]

        number = float(number_str)

        if unit in conversion_factors:
            converted_value = number * conversion_factors[unit]
            rounded_value = long_round(converted_value)

            if rounded_value == int(rounded_value):
                return f'{int(rounded_value)} * mm'
            else:
                return f'{rounded_value} * mm'

        return match.group(0)

    converted_value = re.sub(bracket_pattern, replace_bracket_unit, value_str)
    converted_value = re.sub(pattern, replace_unit, converted_value)
    unit_pattern = r'\b(inch|foot|centimeter|meter)\b'

    def replace_standalone_unit(match):
        unit = match.group(1)
        if unit in conversion_factors:
            return 'mm'
        return match.group(0)

    converted_value = re.sub(unit_pattern, replace_standalone_unit, converted_value)
    converted_value = converted_value.replace('millimeter', 'mm')

    return converted_value
