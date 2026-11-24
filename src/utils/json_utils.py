"""JSON normalization shared by agent adapters and tool execution."""

import math
from typing import Any


def normalize_nonfinite(value: Any) -> Any:
    """Copy JSON containers, replacing non-finite floats with null values.

    Strings remain literal text. Unknown types retain their caller's existing
    serialization policy; no original result or tool-call argument is mutated.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: normalize_nonfinite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        normalized = [normalize_nonfinite(item) for item in value]
        return tuple(normalized) if isinstance(value, tuple) else normalized
    return value
