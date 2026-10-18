"""Vendor-neutral program submission contracts for installed execution plugins."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ProgramExecutionRequest:
    input_paths: tuple[Path, ...]
    driver_name: str
    config_path: Path | None = None
    artifacts_dir: Path | None = None
    fail_ops: frozenset[str] = field(default_factory=frozenset)
    material_state_path: Path | None = None
    inventory_check: bool | dict[str, Any] | None = None
    library_roots: tuple[Path, ...] = ()


class ProgramExecutorPort(Protocol):
    def execute(self, request: ProgramExecutionRequest) -> dict[str, Any]: ...


class ProgramExecutorFactory(Protocol):
    def build(self) -> ProgramExecutorPort: ...


class ProgramExecutionError(ValueError):
    pass
