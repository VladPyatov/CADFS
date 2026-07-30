from dataclasses import dataclass


@dataclass
class Operation:
    """One feature operation extracted from a document.

    ``name`` is the FeatureScript feature name, ``text`` its operation block, and ``type``
    the classification ('sketch' or a geometric op keyword) filled in after extraction.
    """

    name: str
    text: str
    type: str | None = None
