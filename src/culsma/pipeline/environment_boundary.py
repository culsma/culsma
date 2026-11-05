"""Public environment projection for plans, checkpoints and external executors.

Source `rh` and legacy wire `rh` become `humidity`. No conditions or defaults are
invented. Runtime callers must resolve each environment expression first.
"""

from copy import deepcopy

from culsma.common.quantity_arithmetic import QuantityDimension
from culsma.domains.environment import (
    ENVIRONMENT_DIMENSIONS, ENVIRONMENT_MODIFIERS, SOURCE_ENVIRONMENT_KEYS,
    EnvironmentKey, EnvironmentValueError,
    validate_environment_gas_total, validate_environment_quantity,
)


WIRE_ENVIRONMENT_KEYS = SOURCE_ENVIRONMENT_KEYS | {key.value: key for key in EnvironmentKey}


class EnvironmentParameterNormalizer:
    def normalize_plan_environment(self, environment):
        return {key.value: value for key, value in self._decode_environment(environment).items()}

    @staticmethod
    def _decode_environment(environment) -> dict[EnvironmentKey, object]:
        if not isinstance(environment, dict):
            raise EnvironmentValueError("env must be a mapping", reason="structure")
        result = {}
        for name, value in deepcopy(environment).items():
            key = WIRE_ENVIRONMENT_KEYS.get(name)
            if key is None:
                continue
            if key in result:
                raise EnvironmentValueError("env cannot supply both rh and humidity", reason="duplicate")
            result[key] = value
        unknown = set(environment) - WIRE_ENVIRONMENT_KEYS.keys()
        if unknown:
            raise EnvironmentValueError(f"Unknown environment conditions: {sorted(map(str, unknown))}", reason="name")
        return result

    def normalize_runtime_environment(self, environment, *, require_duration=False):
        result = self._decode_environment(environment)
        if EnvironmentKey.THERMAL not in result and EnvironmentKey.FIELD not in result:
            raise EnvironmentValueError("env requires thermal or field", reason="combination")
        has_thermal = EnvironmentKey.THERMAL in result
        has_duration = EnvironmentKey.DURATION in result
        thermal = result.get(EnvironmentKey.THERMAL)
        program = isinstance(thermal, dict) and thermal.get("kind") == "IRCall" and thermal.get("name") == "thermal_program"
        if ENVIRONMENT_MODIFIERS.intersection(result) and (not has_thermal or program):
            raise EnvironmentValueError("env co2/o2/humidity require scalar thermal", reason="combination")
        if has_duration and (not has_thermal or program):
            raise EnvironmentValueError("env duration requires scalar thermal", reason="combination")
        if require_duration and has_thermal and not program and not has_duration:
            raise EnvironmentValueError("Pure scalar environment hold requires duration", reason="combination")
        percentages = {}
        for key, value in result.items():
            if key is EnvironmentKey.FIELD or (key is EnvironmentKey.THERMAL and program):
                continue
            if isinstance(value, tuple) and len(value) == 2:
                value = {"kind": "IRQuantity", "value": value[0], "unit": value[1]}
                result[key] = value
            if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
                raise EnvironmentValueError(f"env {key.value} must resolve to a quantity", reason="unresolved")
            validate_environment_quantity(key, value.get("value"), value.get("unit"))
            if ENVIRONMENT_DIMENSIONS[key] is QuantityDimension.PERCENT:
                percentages[key] = value["value"]
                if value["unit"] == "pct":
                    result[key] = {**value, "unit": "%"}
        validate_environment_gas_total(percentages)
        return {key.value: value for key, value in result.items()}

    def normalize_runtime_gate(self, gate, *, resolve_environment=lambda value: value, require_duration=False):
        """Normalize every layer, preserving target references and unrelated gates."""
        if gate is None:
            return None
        if not isinstance(gate, dict):
            raise EnvironmentValueError("gate must be a mapping", reason="structure")
        result = deepcopy(gate)
        if "env" in result:
            result["env"] = self.normalize_runtime_environment(
                resolve_environment(result["env"]), require_duration=require_duration)
        if "env_layers" in result:
            layers = result["env_layers"]
            if not isinstance(layers, list) or any(not isinstance(layer, dict) or "env" not in layer for layer in layers):
                raise EnvironmentValueError("env_layers must contain environment mappings", reason="structure")
            for index, layer in enumerate(layers):
                layer["env"] = self.normalize_runtime_environment(
                    resolve_environment(layer["env"]),
                    require_duration=require_duration and index == len(layers) - 1)
            if result["env_layers"] and "env" in result and result["env"] != result["env_layers"][-1]["env"]:
                raise EnvironmentValueError("Innermost env layer disagrees with gate.env", reason="structure")
        return result


DEFAULT_ENVIRONMENT_PARAMETER_NORMALIZER = EnvironmentParameterNormalizer()
