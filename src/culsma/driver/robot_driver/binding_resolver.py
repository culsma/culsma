"""Resolve robot-facing binding context."""

from __future__ import annotations

from culsma.driver.framework.contracts import DriverContext
from culsma.driver.framework.mapping_core import value_to_text
from culsma.driver.framework.models import MappingRecord

_ACTION_BY_OP = {
    "Mutation": "material.transfer",
    "sep": "material.separate",
    "frac": "material.fractionate",
    "img": "observe.image",
    "ecp": "observe.electrochemical",
    "phy": "observe.physical",
    "env_hold": "environment.hold",
    "agit": "material.agitate",
}

_ACTION_BY_PROGRAM_KIND = {
    "centrifuge_program": "device.centrifuge.run",
    "filtration_program": "device.filter.run",
    "phase_partition_program": "material.separate.phase_partition",
    "density_gradient_program": "device.fractionation.run",
    "chromatography_program": "device.chromatography.run",
    "temperature_program": "sensor.temperature.read",
    "pressure_program": "sensor.pressure.read",
    "optical_fluor_program": "device.reader.fluor.read",
    "optical_uv_program": "device.reader.uv.read",
}


class RobotBindingResolver:
    def bind(self, record: MappingRecord, context: DriverContext | None = None) -> dict[str, Any]:
        return {
            "action": _ACTION_BY_PROGRAM_KIND.get(
                record.program_kind or "",
                _ACTION_BY_OP.get(record.semantic_op, f"generic.{record.semantic_op.lower()}"),
            ),
            "requirement_flags": list(record.requirements),
            "env_summary": (
                {key: value_to_text(value) for key, value in sorted(record.env.items())}
                if isinstance(record.env, dict)
                else {}
            ),
            "driver_kind": context.driver_kind if context is not None else "robot",
            "program_kind": record.program_kind,
        }
