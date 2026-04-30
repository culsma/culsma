"""Driver HAL base contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from culsma.pipeline.plan_nodes import PlanStep


@dataclass(frozen=True)
class DriverResult:
    ok: bool
    code: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverCapabilityResult:
    ok: bool
    code: str
    unsupported_requirements: tuple[str, ...] = ()
    unsupported_constraint_options: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)


class Driver(Protocol):
    def check(self, step: PlanStep) -> DriverCapabilityResult:
        """Check whether driver can execute one plan step under its current constraints."""
        ...

    def execute(self, step: PlanStep) -> DriverResult:
        """Execute one plan step and return structured result."""
        ...
