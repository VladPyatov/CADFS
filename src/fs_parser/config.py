from dataclasses import dataclass


@dataclass
class ParseConfig:
    """Tunable settings for a parse run, shared by Parser and its sub-parsers.
    """

    default_space: str = '            '
    operation_limit: int = -1
    debug: bool = False
