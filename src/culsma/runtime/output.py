"""Console formatting for the language print statement."""

from __future__ import annotations

import math
from typing import Any
from culsma.runtime.value_adapters import AdaptedValue, create_value_adapter_registry
from culsma.runtime.value_adapters.contracts import QuantityDisplayValue


def format_print_value(value: Any, *, nested: bool = False, registry=None) -> str:
    """Format a complete value without interpreting record fields as executable code."""
    if isinstance(value, AdaptedValue):
        registry = registry if registry is not None else create_value_adapter_registry()
        adapter = registry.resolve(value.type_id)
        if adapter is None:
            raise ValueError(f'No value adapter for {value.type_id}')
        return format_print_value(adapter.describe(value), nested=nested, registry=registry)
    if value is None or isinstance(value, (bool, int)):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return str(value)
    if isinstance(value, str):
        return repr(value) if nested else value
    if isinstance(value, list):
        return '[' + ', '.join(format_print_value(item, nested=True, registry=registry) for item in value) + ']'
    if isinstance(value, dict):
        if isinstance(value, QuantityDisplayValue):
            amount = value['value']
            if isinstance(amount, float) and not math.isfinite(amount):
                raise ValueError("non-finite quantity")
            number = str(int(amount)) if amount == int(amount) else str(amount)
            return f"{number} {value['unit']}"
        return '{' + ', '.join(
            f'{key!r}: {format_print_value(item, nested=True, registry=registry)}' for key, item in value.items()
        ) + '}'
    raise TypeError(f"unsupported print value: {type(value).__name__}")
