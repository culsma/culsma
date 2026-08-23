"""Stable runtime report models and their JSON projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LAB_REPORT_SCHEMA = "lab_report_v1"

@dataclass(frozen=True)
class ExecutionSummary:
    ok: bool
    diagnostic_count: int
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "diagnostic_count": self.diagnostic_count,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
        }


@dataclass(frozen=True)
class InputInventoryRow:
    name: str
    initial_uL: float
    initial_mL: float
    initial_mg: float
    initial_cells: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "initial_uL": self.initial_uL,
            "initial_mL": self.initial_mL,
            "initial_mg": self.initial_mg,
        }
        if self.initial_cells > 0.0:
            out["initial_cells"] = self.initial_cells
        return out


@dataclass(frozen=True)
class FinalProductRow:
    name: str
    volume_uL: float
    volume_mL: float
    mass_mg: float | None
    primary_component: str | None
    count_cells: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "volume_uL": self.volume_uL,
            "volume_mL": self.volume_mL,
            "mass_mg": self.mass_mg,
            "primary_component": self.primary_component,
        }
        if self.count_cells > 0.0:
            out["count_cells"] = self.count_cells
        return out


@dataclass(frozen=True)
class IntermediateMaterialRow:
    name: str
    final_uL: float
    final_mL: float
    mass_mg: float | None
    primary_component: str | None
    count_cells: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "final_uL": self.final_uL,
            "final_mL": self.final_mL,
            "mass_mg": self.mass_mg,
            "primary_component": self.primary_component,
        }
        if self.count_cells > 0.0:
            out["count_cells"] = self.count_cells
        return out


@dataclass(frozen=True)
class ReagentConsumptionRow:
    name: str
    roles: list[str]
    consumed_uL: float | None
    consumed_mL: float | None
    consumed_mg: float | None
    consumed_cells: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "roles": list(self.roles),
            "consumed_uL": self.consumed_uL,
            "consumed_mL": self.consumed_mL,
            "consumed_mg": self.consumed_mg,
        }
        if self.consumed_cells is not None:
            out["consumed_cells"] = self.consumed_cells
        return out


@dataclass(frozen=True)
class MaterialsReport:
    has_material_state: bool
    input_inventory: list[InputInventoryRow] = field(default_factory=list)
    final_products: list[FinalProductRow] = field(default_factory=list)
    intermediate_materials: list[IntermediateMaterialRow] = field(default_factory=list)
    reagent_consumption: list[ReagentConsumptionRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_material_state": self.has_material_state,
            "input_inventory": [row.to_dict() for row in self.input_inventory],
            "final_products": [row.to_dict() for row in self.final_products],
            "intermediate_materials": [row.to_dict() for row in self.intermediate_materials],
            "reagent_consumption": [row.to_dict() for row in self.reagent_consumption],
        }


@dataclass(frozen=True)
class ContainerKindCount:
    kind: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "count": self.count}


@dataclass(frozen=True)
class NamedCount:
    name: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count}


@dataclass(frozen=True)
class ContainerResourceSummary:
    allocated_count: int
    touched_count: int
    container_kinds: list[ContainerKindCount]
    touched_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allocated_count": self.allocated_count,
            "touched_count": self.touched_count,
            "container_kinds": [item.to_dict() for item in self.container_kinds],
            "touched_names": list(self.touched_names),
        }


@dataclass(frozen=True)
class InstrumentSummary:
    tools: list[NamedCount]
    devices: list[NamedCount]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": [item.to_dict() for item in self.tools],
            "devices": [item.to_dict() for item in self.devices],
        }


@dataclass(frozen=True)
class ResourceSummary:
    containers: ContainerResourceSummary
    instruments: InstrumentSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "containers": self.containers.to_dict(),
            "instruments": self.instruments.to_dict(),
        }


@dataclass(frozen=True)
class ProcessSummary:
    mutation_steps: int = 0
    separation_steps: int = 0
    environment_steps: int = 0
    readout_steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_steps": self.mutation_steps,
            "separation_steps": self.separation_steps,
            "environment_steps": self.environment_steps,
            "readout_steps": self.readout_steps,
        }


@dataclass(frozen=True)
class QcResult:
    item: str
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.values, "item": self.item}


@dataclass(frozen=True)
class LabReport:
    execution: ExecutionSummary
    headline: str
    materials: MaterialsReport
    qc_results: list[QcResult]
    resource_summary: ResourceSummary
    process_summary: ProcessSummary
    alerts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAB_REPORT_SCHEMA,
            "execution": self.execution.to_dict(),
            "headline": self.headline,
            "materials": self.materials.to_dict(),
            "qc_results": [result.to_dict() for result in self.qc_results],
            "resource_summary": self.resource_summary.to_dict(),
            "process_summary": self.process_summary.to_dict(),
            "alerts": list(self.alerts),
        }
