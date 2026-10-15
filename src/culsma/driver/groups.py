"""Vendor-neutral optional prepared group execution boundary."""
from dataclasses import dataclass
from typing import Any, Protocol
from culsma.driver.base import DriverCapabilityResult, DriverResult
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.result import MaterialUpdateResult


@dataclass(frozen=True)
class PreparedDriverStep:
    runtime_step: PlanStep
    driver_step: PlanStep
    material_result: MaterialUpdateResult | None
    before_material_state: dict[str, Any]
    capability: DriverCapabilityResult


@dataclass(frozen=True)
class PreparedExecutionGroup:
    step_id: str
    members: tuple[PreparedDriverStep, ...]
    source_member_ids: tuple[str, ...]


@dataclass(frozen=True)
class GroupDriverResult:
    member_ids: tuple[str, ...]
    results: tuple[DriverResult, ...]


class GroupDriver(Protocol):
    supports_group_execution: bool

    def execute_group(self, group: PreparedExecutionGroup) -> GroupDriverResult: ...
