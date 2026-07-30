from dataclasses import dataclass, field


@dataclass
class ParseContext:
    """Mutable state shared across the sub-parsers during one document parse.
    """

    sketches: dict = field(default_factory=dict)  # featureId -> Sketch
    unreported_sketches: list = field(default_factory=list)
    feature_names: dict = field(default_factory=dict)  # long name -> short (F0..)
    entities: dict = field(default_factory=dict)  # long name -> short (E0..)
    duplicated_entities: dict = field(default_factory=dict)
    geometric_operations: dict = field(default_factory=dict)
    broken_geometry: list = field(default_factory=list)
