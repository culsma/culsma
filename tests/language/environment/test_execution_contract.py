"""Source-to-executor propagation and the JSON public environment boundary."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from culsma.driver.stub import StubDriver
from culsma.pipeline.external_boundary import DEFAULT_ENVIRONMENT_PARAMETER_NORMALIZER as NORMALIZER
from culsma.pipeline.ir_nodes import IRWithEnv
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.executor import run


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.steps = []

    def execute(self, step):
        self.steps.append(deepcopy(step))
        return super().execute(step)


def test_omitted_and_explicit_conditions_stay_distinct(build_plan, env_source):
    for extra, expected in [
        ("", set()), (", co2=0%", {"co2"}),
        (", co2=5%, o2=20%, rh=80%", {"co2", "o2", "humidity"}),
    ]:
        plan = build_plan(env_source("thermal=22C, duration=1min" + extra))
        driver = RecordingDriver()
        result = run(plan, driver)
        assert result.ok, result.diagnostics
        step = next(step for step in driver.steps if step.op == "env_hold")
        env = step.gate["env"]
        assert set(env) == {"thermal", "duration"} | expected
        assert env["thermal"]["value"] == 22
        assert env["thermal"]["unit"] == "C"
        if "co2" in expected:
            assert env["co2"]["value"] == (0 if expected == {"co2"} else 5)


def test_environment_round_trip(compile_source, build_plan, env_source):
    source = env_source("thermal=22C, duration=1min, co2=5%, o2=20%, rh=80%")
    compiled = compile_source(source)
    env_ir = compiled.ir.protocols[0].statements[-1]
    assert isinstance(env_ir, IRWithEnv)
    assert {arg.name for arg in env_ir.env_args} == {"thermal", "duration", "co2", "o2", "rh"}
    plan = build_plan(source)
    payload = json.loads(json.dumps(plan.to_dict()))
    steps = [PlanStep(step_id=s["step_id"], op=s["op"], args=s["args"], deps=s["deps"], gate=s["gate"])
             for s in payload["plans"][0]["steps"]]
    restored = PlanProgram(plans=[ProtocolPlan("restored", "T", steps=steps)])
    driver = RecordingDriver()
    result = run(restored, driver)
    assert result.ok, result.diagnostics
    hold = next(step for step in driver.steps if step.op == "env_hold")
    assert hold.gate["env"] == steps[-1].gate["env"]
    assert hold.gate["env"] == hold.gate["env_layers"][-1]["env"]
    assert {k: v["value"] for k, v in hold.gate["env"].items()} == {
        "thermal": 22, "duration": 1, "co2": 5, "o2": 20, "humidity": 80}
    completed = next(e for e in result.events if e.kind == "STEP_COMPLETED" and e.step_id == hold.step_id)
    assert completed.payload["gate"]["env"] == hold.gate["env"]
    assert "material_delta" not in completed.payload


def test_legacy_humidity_boundary():
    payload = {"thermal": {"kind": "IRQuantity", "value": 22, "unit": "C"},
               "duration": {"kind": "IRQuantity", "value": 1, "unit": "min"},
               "rh": {"kind": "IRQuantity", "value": 80, "unit": "pct"}}
    original = deepcopy(payload)
    result = NORMALIZER.normalize_runtime_environment(json.loads(json.dumps(payload)))
    assert result["humidity"]["value"] == 80
    assert result["humidity"]["unit"] == "%"
    assert payload == original
    assert "rh" not in result
    assert NORMALIZER.normalize_runtime_environment(result) == result
    with pytest.raises(ValueError, match="both rh and humidity"):
        NORMALIZER.normalize_runtime_environment({**payload, "humidity": payload["rh"]})


def test_nested_environment_layers(build_plan):
    plan = build_plan('''protocol T { let sample=tube();
      with env(thermal=22C, duration=2min, co2=5%, rh=80%) {
        with env(thermal=37C, duration=1min, o2=20%) {
          img(sample=sample, quantity=fluorescence);
        }
      }
    }''')
    driver = RecordingDriver()
    result = run(plan, driver)
    assert result.ok, result.diagnostics
    step = next(step for step in driver.steps if step.op == "img")
    outer, inner = step.gate["env_layers"]
    assert set(outer["env"]) == {"thermal", "duration", "co2", "humidity"}
    assert set(inner["env"]) == {"thermal", "duration", "o2"}
    assert step.gate["env"] == inner["env"]
    assert "humidity" not in step.gate["env"]


def test_cell_transfection_preserves_22c_requirements(build_plan):
    source = (Path(__file__).resolve().parents[3] /
              "benchmarks/modules/01-cell-transfection/protocol.culs").read_text()
    plan = build_plan(source)  # Compile only; no benchmark or instrument execution.
    holds = [step for protocol in plan.plans for step in protocol.steps if step.op == "env_hold"]
    assert len(holds) == 4
    assert [step.gate["env"]["thermal"]["value"] for step in holds] == [37, 22, 22, 37]
    for step in holds:
        env = step.gate["env"]
        assert env["thermal"]["unit"] == "C"
        expected = {"thermal", "duration", "co2"} if env["thermal"]["value"] == 37 else {"thermal", "duration"}
        assert set(env) == expected


def test_active_operation_omits_duration_without_default(build_plan, env_source):
    plan = build_plan(env_source("thermal=22C, rh=80%", 'img(sample=sample, quantity=fluorescence);'))
    driver = RecordingDriver()
    result = run(plan, driver)
    assert result.ok, result.diagnostics
    active = next(step for step in driver.steps if step.op == "img")
    assert set(active.gate["env"]) == {"thermal", "humidity"}


@pytest.mark.parametrize("gate", [
    {"env_layers": None}, {"env_layers": [None]}, {"env_layers": [{}]},
    {"env": {"thermal": {"kind": "IRQuantity", "value": 22, "unit": "C"}},
     "env_layers": [{"env": {"thermal": {"kind": "IRQuantity", "value": 37, "unit": "C"}}}]},
])
def test_malformed_or_disagreeing_gate_is_rejected(gate):
    with pytest.raises(ValueError):
        NORMALIZER.normalize_runtime_gate(gate)
