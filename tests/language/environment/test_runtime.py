"""Late binding must be validated before capability checks or device execution."""
from copy import deepcopy
from dataclasses import replace

import pytest

from culsma.driver.base import DriverCapabilityResult
from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run


class EnvironmentDriver(StubDriver):
    def __init__(self, unsupported=()):
        super().__init__(op_payloads={"img": {"result": {"signal": 1}}})
        self.unsupported = set(unsupported)
        self.checked = []
        self.executed = []

    def check(self, step):
        self.checked.append(step)
        unsupported = self.unsupported.intersection((step.gate or {}).get("env", {}))
        if unsupported:
            return DriverCapabilityResult(False, "ENV_UNSUPPORTED", tuple(sorted(unsupported)))
        return super().check(step)

    def execute(self, step):
        self.executed.append(step)
        return super().execute(step)


@pytest.mark.parametrize("name,value,ok", [
    ("thermal", "22C", True), ("thermal", "-274C", False),
    ("duration", "1min", True), ("duration", "0s", False),
    ("co2", "0%", True), ("co2", "-1%", False),
    ("o2", "20%", True), ("o2", "101%", False),
    ("rh", "80%", True), ("rh", "101%", False),
])
def test_deferred_environment_validation(build_plan, name, value, ok):
    defaults = {"thermal": "22C", "duration": "1min", "co2": "5%", "o2": "20%", "rh": "80%"}
    args = ", ".join(f"{k}=" + ("value" if k == name else v) for k, v in defaults.items())
    plan = build_plan(f'''let sample=tube(); let value={defaults[name]};
      let observation=img(sample=sample, quantity=fluorescence);
      if observation.result.signal > 0 {{ value={value}; }}
      else {{ value={defaults[name]}; }}
      with env({args}) {{ hold(sample); }}''')
    driver = EnvironmentDriver()
    result = run(plan, driver)
    assert result.ok == ok, result.diagnostics
    holds = [step for step in driver.executed if step.op == "env_hold"]
    assert bool(holds) == ok
    if not ok:
        assert "RT_ENV_ARGUMENT_INVALID" in [d.code for d in result.diagnostics]
        assert not [step for step in driver.checked if step.op == "env_hold"]
    else:
        wire_name = "humidity" if name == "rh" else name
        assert holds[0].gate["env"][wire_name]["kind"] == "IRQuantity"


@pytest.mark.parametrize("name", ["co2", "o2", "humidity"])
def test_unsupported_environment_rejected_before_execute(build_plan, name):
    plan = build_plan('''let sample=tube();
      with env(thermal=22C, duration=1min, co2=5%, o2=20%, rh=80%) { hold(sample); }''')
    driver = EnvironmentDriver({name})
    result = run(plan, driver)
    assert not result.ok
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in [d.code for d in result.diagnostics]
    assert not [step for step in driver.executed if step.op == "env_hold"]
    checked = next(step for step in driver.checked if step.op == "env_hold")
    assert set(checked.gate["env"]) == {"thermal", "duration", "co2", "o2", "humidity"}


@pytest.mark.parametrize("bad", [
    {"o2": {"kind": "IRQuantity", "value": 20, "unit": "min"}},
    {"o2": {"kind": "IRQuantity", "value": float("nan"), "unit": "%"}},
    {"o2": {"kind": "IRIdentifier", "name": "missing"}},
    {"o2": None}, {"unknown": 5},
    {"co2": {"kind": "IRQuantity", "value": 90, "unit": "%"},
     "o2": {"kind": "IRQuantity", "value": 20, "unit": "%"}},
])
def test_serialized_invalid_environment_fails_closed(build_plan, bad):
    plan = build_plan('let sample=tube(); with env(thermal=22C, duration=1min) { hold(sample); }')
    hold = plan.plans[0].steps[-1]
    gate = deepcopy(hold.gate)
    gate["env"].update(bad)
    gate["env_layers"][-1]["env"] = deepcopy(gate["env"])
    plan = replace(plan, plans=[replace(plan.plans[0], steps=[*plan.plans[0].steps[:-1], replace(hold, gate=gate)])])
    driver = EnvironmentDriver()
    result = run(plan, driver)
    assert not result.ok
    assert "RT_ENV_ARGUMENT_INVALID" in [d.code for d in result.diagnostics]
    assert not [step for step in driver.executed if step.op == "env_hold"]


def test_legacy_wire_rh_reaches_canonical_driver_environment(build_plan):
    plan = build_plan('let sample=tube(); with env(thermal=22C, duration=1min, rh=80%) { hold(sample); }')
    hold = plan.plans[0].steps[-1]
    # gate.env and the layer may alias in an in-memory plan, as in older plans.
    gate = deepcopy(hold.gate)
    for env in [gate["env"], gate["env_layers"][-1]["env"]]:
        if "humidity" in env:
            env["rh"] = env.pop("humidity")
    legacy = replace(plan, plans=[replace(plan.plans[0], steps=[*plan.plans[0].steps[:-1], replace(hold, gate=gate)])])
    driver = EnvironmentDriver()
    result = run(legacy, driver)
    assert result.ok, result.diagnostics
    runtime = next(step for step in driver.executed if step.op == "env_hold")
    assert runtime.gate["env"]["humidity"]["value"] == 80
    assert "rh" not in runtime.gate["env"]
    assert "rh" in legacy.plans[0].steps[-1].gate["env"]


def test_thermal_program_parameter_does_not_require_outer_duration(build_plan):
    plan = build_plan('''protocol T(temp) {
      let sample=tube(); with env(thermal=temp) { hold(sample); }
    }
    T(temp=thermal_program(from=22C, duration=1min));''')
    driver = EnvironmentDriver()
    result = run(plan, driver)
    assert result.ok, result.diagnostics
    hold = next(step for step in driver.executed if step.op == "env_hold")
    assert hold.gate["env"]["thermal"]["name"] == "thermal_program"
    assert "duration" not in hold.gate["env"]
