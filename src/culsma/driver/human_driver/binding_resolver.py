"""Resolve human-facing binding context for mapping records."""

from __future__ import annotations

from typing import Any

from culsma.driver.framework.contracts import DriverContext

from .mapping_core import value_to_text
from .models import HumanMappingRecord
from .mutation_strategy import resolve_mutation_strategy

_REQUIREMENT_NOTES = {
    "gentle": "Handle gently and avoid abrupt disturbance.",
    "aseptic": "Maintain aseptic handling throughout this step.",
    "low_loss": "Minimize transfer loss during handling.",
    "cold_chain": "Keep material within the required cold-chain conditions.",
    "avoid_resuspension": "Avoid disturbing settled material while handling.",
}

_DEFAULT_TOOL_BY_OP = {
    "Mutation": "manual transfer workflow",
    "sep": "manual separation workflow",
    "frac": "manual fraction collection workflow",
    "img": "manual imaging/readout workflow",
    "ecp": "manual electrochemical readout workflow",
    "phy": "manual physical readout workflow",
    "env_hold": "manual environment hold workflow",
    "agit": "manual agitation workflow",
    "AllocContainer": "setup workflow",
    "LoadContent": "setup workflow",
    "DefineContent": "setup workflow",
}

_TOOL_BY_PROGRAM_KIND = {
    "centrifuge_program": "manual centrifuge workflow",
    "filtration_program": "manual filtration workflow",
    "phase_partition_program": "manual phase-partition workflow",
    "density_gradient_program": "manual density-gradient workflow",
    "chromatography_program": "manual chromatography workflow",
}

_TOOL_BY_READOUT_QUANTITY = {
    ("img", "uv_absorbance"): "UV absorbance readout workflow",
    ("img", "fluorescence"): "fluorescence readout workflow",
    ("img", "colorimetric"): "colorimetric readout workflow",
    ("ecp", "ph"): "pH probe workflow",
    ("ecp", "conductivity"): "conductivity probe workflow",
    ("ecp", "dissolved_oxygen"): "dissolved oxygen probe workflow",
    ("ecp", "orp"): "ORP probe workflow",
    ("phy", "temperature"): "temperature probe workflow",
    ("phy", "pressure"): "pressure probe workflow",
    ("phy", "flow_rate"): "flow-rate sensor workflow",
    ("phy", "mass"): "mass measurement workflow",
    ("phy", "volume"): "volume measurement workflow",
    ("phy", "humidity"): "humidity sensor workflow",
    ("phy", "current"): "current measurement workflow",
}


class HumanBindingResolver:
    """Resolve human-readable binding hints from normalized records."""

    def bind(self, record: HumanMappingRecord, context: DriverContext | None = None) -> dict[str, Any]:
        tool_label = _tool_label_for_record(record)
        requirement_notes = tuple(
            _REQUIREMENT_NOTES.get(requirement, f"Honor requirement '{requirement}'.")
            for requirement in record.requirements
        )
        env_summary = None
        if isinstance(record.env, dict) and record.env:
            env_summary = ", ".join(f"{key}={value_to_text(val)}" for key, val in sorted(record.env.items()))
        binding: dict[str, Any] = {
            "tool_label": tool_label,
            "requirement_notes": requirement_notes,
            "env_summary": env_summary,
            "driver_kind": context.driver_kind if context is not None else "human",
            "program_kind": record.program_kind,
        }
        if record.semantic_op == "Mutation":
            strategy = resolve_mutation_strategy(record)
            binding.update(strategy)
            binding["tool_label"] = strategy["pipette_label"]
        return binding


def _tool_label_for_record(record: HumanMappingRecord) -> str:
    program_label = _TOOL_BY_PROGRAM_KIND.get(record.program_kind or "")
    if program_label is not None:
        return program_label
    quantity = value_to_text(record.semantic_args.get("quantity"))
    quantity_label = _TOOL_BY_READOUT_QUANTITY.get((record.semantic_op, quantity))
    if quantity_label is not None:
        return quantity_label
    return _DEFAULT_TOOL_BY_OP.get(record.semantic_op, "manual workflow")
