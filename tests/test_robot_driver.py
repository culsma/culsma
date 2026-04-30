from __future__ import annotations

from culsma.driver.robot import RobotDriver
from culsma.pipeline.plan_nodes import PlanStep


def test_robot_driver_emits_structured_mutation_command_payload():
    step = PlanStep(
        step_id="step.robot.1",
        op="Mutation",
        args={
            "target": {"kind": "IRIdentifier", "name": "dst"},
            "sources": [
                {
                    "kind": "IRPair",
                    "left": {"kind": "IRIdentifier", "name": "src"},
                    "right": {"kind": "IRQuantity", "value": 5, "unit": "uL"},
                }
            ],
        },
        gate={"constraint": {"requirements": ["gentle"]}},
    )

    result = RobotDriver().execute(step)

    assert result.ok
    assert result.code == "DRV_ROBOT_OK"
    assert result.payload["driver_kind"] == "robot"
    assert result.payload["command"]["label"] == "Mutation command"
    assert result.payload["binding"]["action"] == "material.transfer"
    assert result.payload["binding"]["requirement_flags"] == ["gentle"]


def test_robot_driver_preserves_stub_payload_for_observation_results():
    step = PlanStep(
        step_id="step.robot.obs.1",
        op="phy",
        args={"sample": {"kind": "IRIdentifier", "name": "probe"}},
    )

    result = RobotDriver(op_payloads={"phy": {"result": {"temperature": 22.5}}}).execute(step)

    assert result.ok
    assert result.payload["result"]["temperature"] == 22.5
    assert result.payload["command"]["category"] == "command"


def test_robot_driver_prefers_program_kind_specific_action_binding():
    step = PlanStep(
        step_id="step.robot.obs.2",
        op="phy",
        args={
            "sample": {"kind": "IRIdentifier", "name": "probe"},
            "program": {
                "kind": "IRCall",
                "name": "temperature_program",
                "args": [{"name": "mode", "value": {"kind": "IRString", "value": "single"}}],
            },
        },
    )

    result = RobotDriver().execute(step)

    assert result.ok
    assert result.payload["binding"]["program_kind"] == "temperature_program"
    assert result.payload["binding"]["action"] == "sensor.temperature.read"
