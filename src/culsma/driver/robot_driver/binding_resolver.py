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
}

_ACTION_BY_READOUT_QUANTITY = {
    ("img", "uv_absorbance"): "device.reader.uv.read",
    ("img", "fluorescence"): "device.reader.fluor.read",
    ("img", "colorimetric"): "device.reader.colorimetric.read",
    ("ecp", "ph"): "sensor.ph.read",
    ("ecp", "conductivity"): "sensor.conductivity.read",
    ("ecp", "dissolved_oxygen"): "sensor.dissolved_oxygen.read",
    ("ecp", "orp"): "sensor.orp.read",
    ("phy", "temperature"): "sensor.temperature.read",
    ("phy", "pressure"): "sensor.pressure.read",
    ("phy", "flow_rate"): "sensor.flow_rate.read",
    ("phy", "mass"): "sensor.mass.read",
    ("phy", "volume"): "sensor.volume.read",
    ("phy", "humidity"): "sensor.humidity.read",
    ("phy", "current"): "sensor.current.read",
}


class RobotBindingResolver:
    def bind(self, record: MappingRecord, context: DriverContext | None = None) -> dict[str, Any]:
        return {
            "action": _action_for_record(record),
            "requirement_flags": list(record.requirements),
            "env_summary": (
                {key: value_to_text(value) for key, value in sorted(record.env.items())}
                if isinstance(record.env, dict)
                else {}
            ),
            "driver_kind": context.driver_kind if context is not None else "robot",
            "program_kind": record.program_kind,
        }


def _action_for_record(record: MappingRecord) -> str:
    program_action = _ACTION_BY_PROGRAM_KIND.get(record.program_kind or "")
    if program_action is not None:
        return program_action
    quantity = value_to_text(record.semantic_args.get("quantity"))
    quantity_action = _ACTION_BY_READOUT_QUANTITY.get((record.semantic_op, quantity))
    if quantity_action is not None:
        return quantity_action
    return _ACTION_BY_OP.get(record.semantic_op, f"generic.{record.semantic_op.lower()}")
