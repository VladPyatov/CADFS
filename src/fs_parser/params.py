import re

from src.fs_parser.values import clean_try_expression


def parse_param_block(params_text: str, *, clean_values: bool = True) -> dict:
    """Parse a FeatureScript object body (the text between the outermost braces).
    """
    params_dict = {}
    i = 0
    while i < len(params_text):
        if params_text[i] != '"':
            i += 1
            continue

        key_start = i + 1
        key_end = params_text.find('"', key_start)
        if key_end == -1:
            break
        key = params_text[key_start:key_end]

        colon_pos = params_text.find(':', key_end)
        if colon_pos == -1:
            break

        value_start = colon_pos + 1
        while value_start < len(params_text) and params_text[value_start].isspace():
            value_start += 1

        bracket_count = paren_count = brace_count = 0
        value_end = value_start
        while value_end < len(params_text):
            char = params_text[value_end]
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
            elif char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
            elif char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == ',' and bracket_count == 0 and paren_count == 0 and brace_count == 0:
                break
            value_end += 1

        value = params_text[value_start:value_end].strip()
        if value.endswith(','):
            value = value[:-1].strip()
        if clean_values:
            value = clean_try_expression(value)

        params_dict[key] = value
        i = value_end + 1

    return params_dict


# --- predicates shared across operation filters -----------------------------


def is_true(val) -> bool:
    return val is True or (isinstance(val, str) and val.lower() == 'true')


def is_false(val) -> bool:
    return val is False or (isinstance(val, str) and val.lower() == 'false')


def is_empty_query(val) -> bool:
    """True for an empty selection: ``qUnion([])``, ``[]`` or ``qUnion( [ ] )``."""
    if val in ('qUnion([])', '[]'):
        return True
    return isinstance(val, str) and re.match(r'qUnion\(\s*\[\s*\]\s*\)', val) is not None


def is_zero_length(val):
    """Truthy for ``0.0 * <length-unit>`` (mirrors the original re.match result)."""
    if isinstance(val, str):
        return re.match(r'0\.0\s*\*\s*(inch|meter|millimeter|centimeter|foot)', val)
    return False


# --- shared query-definition line filter ------------------------------------

_QUERY_FUNCS = (
    'qSketchRegion',
    'sketchEntityQuery',
    'qConstructionFilter',
    'qBodyType',
    'qCreatedBy',
    'qNothing',
    'qUnion',
)


def is_query_definition(line: str) -> bool:
    """A line assigning one of the known query builders (``X =qCreatedBy(...)`` etc.).
    """
    return any(f'={func}' in line or f'= {func}' in line for func in _QUERY_FUNCS)
