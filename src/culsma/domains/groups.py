"""Group binding values and static bounds; independent of compiler stages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroupBinding:
    kind: str
    size: int | None = None


def index_bounds_error(binding: GroupBinding, index: int) -> str | None:
    """Return a bounds violation for an already resolved non-negative index.

    Unknown cardinality defers the upper-bound check. The caller owns expression
    resolution, integer/non-negative validation and diagnostic source locations.
    """
    if binding.kind == "sep_container_group" and index not in {0, 1}:
        return "sep_container_group only supports indices 0 and 1"
    if binding.kind == "fraction_group" and binding.size is not None and index >= binding.size:
        return f"fraction_group index {index} is out of range for bins={binding.size}"
    if binding.kind == "data_group" and binding.size is not None and index >= binding.size:
        return f"data_group_ref index {index} is out of range for size={binding.size}"
    if binding.kind == "container_group" and binding.size is not None and index >= binding.size:
        return f"container_group index {index} is out of range for size={binding.size}"
    return None
