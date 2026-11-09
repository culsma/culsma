"""Shared capability policy for driver requirement checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.base import DriverCapabilityResult
from culsma.domains.medium import MediumPhase
from culsma.pipeline.medium_boundary import resolve_medium
from culsma.domains.environment import EnvironmentValueError
from culsma.pipeline.plan_nodes import PlanStep


@dataclass(frozen=True)
class CapabilityPolicy:
    supported_requirements: set[str] | None = None
    supported_constraint_option_keys: set[str] | None = None
    supported_medium_phases: frozenset[MediumPhase] = field(default_factory=frozenset)

    def __post_init__(self):
        if any(type(phase) is not MediumPhase for phase in self.supported_medium_phases):
            raise TypeError("supported_medium_phases requires MediumPhase members")
        object.__setattr__(self, 'supported_medium_phases', frozenset(self.supported_medium_phases))

    def evaluate(self, step: PlanStep) -> DriverCapabilityResult:
        gate = step.gate or {}
        environments = []
        if isinstance(gate, dict):
            environments.append(gate.get('env', {}))
            layers = gate.get('env_layers', [])
            if isinstance(layers, list):
                environments.extend(layer.get('env', {}) for layer in layers if isinstance(layer, dict))
        for environment in environments:
            if isinstance(environment, dict):
                try:
                    medium = resolve_medium(environment)
                except EnvironmentValueError:
                    return DriverCapabilityResult(ok=False, code='DRV_REQ_UNSUPPORTED',
                        unsupported_requirements=('medium',))
                # Omission is the legacy ordinary-atmosphere path. An explicit
                # medium still requires declared execution capability.
                if 'medium' in environment and medium.phase not in self.supported_medium_phases:
                    return DriverCapabilityResult(ok=False, code='DRV_REQ_UNSUPPORTED',
                        unsupported_requirements=('medium',),
                        payload={'step_id': step.step_id, 'op': step.op, 'medium': environment['medium']})
        constraint = gate.get("constraint") if isinstance(gate, dict) else None
        requirements = ()
        option_keys = ()
        if isinstance(constraint, dict):
            raw_requirements = constraint.get("requirements")
            if isinstance(raw_requirements, list):
                requirements = tuple(item for item in raw_requirements if isinstance(item, str))
            raw_options = constraint.get("options")
            if isinstance(raw_options, dict):
                option_keys = tuple(key for key in raw_options.keys() if isinstance(key, str))
        if self.supported_requirements is not None:
            unsupported = tuple(req for req in requirements if req not in self.supported_requirements)
            if unsupported:
                return DriverCapabilityResult(
                    ok=False,
                    code="DRV_REQ_UNSUPPORTED",
                    unsupported_requirements=unsupported,
                    payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
                )
        if self.supported_constraint_option_keys is not None:
            unsupported_options = tuple(key for key in option_keys if key not in self.supported_constraint_option_keys)
            if unsupported_options:
                return DriverCapabilityResult(
                    ok=False,
                    code="DRV_REQ_OPTION_UNSUPPORTED",
                    unsupported_constraint_options=unsupported_options,
                    payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
                )
        return DriverCapabilityResult(
            ok=True,
            code="DRV_REQ_OK",
            payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
        )
