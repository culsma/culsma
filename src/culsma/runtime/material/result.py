"""Material update result values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic


@dataclass(frozen=True)
class MaterialMovementSpec:
    source: str
    destination: str | None
    volume_uL: float = 0.0
    mass_mg: float = 0.0
    count_cells: float = 0.0


@dataclass(frozen=True)
class MaterialUpdateResult:
    material_state: dict[str, Any]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    delta: dict[str, Any] = field(default_factory=dict)
    movements: list[MaterialMovementSpec] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)
