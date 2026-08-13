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


def test_robot_driver_prefers_readout_quantity_specific_action_binding():
    step = PlanStep(
        step_id="step.robot.obs.2",
        op="phy",
        args={
            "sample": {"kind": "IRIdentifier", "name": "probe"},
            "quantity": {"kind": "IRIdentifier", "name": "temperature"},
        },
    )

    result = RobotDriver().execute(step)

    assert result.ok
    assert result.payload["binding"]["program_kind"] is None
    assert result.payload["binding"]["action"] == "sensor.temperature.read"


def test_robot_driver_preserves_centrifugal_filtration_program_parameters():
    step = PlanStep(
        step_id="step.robot.filtration",
        op="sep",
        args={
            "sample": {"kind": "IRIdentifier", "name": "silica_column"},
            "program": {
                "kind": "IRCall",
                "name": "centrifugal_filtration_program",
                "args": [
                    {"name": "membrane", "value": {"kind": "IRString", "value": "silica"}},
                    {
                        "name": "drive",
                        "value": {"kind": "IRQuantity", "value": 8000, "unit": "g"},
                    },
                    {"name": "duration", "value": {"kind": "IRQuantity", "value": 1, "unit": "min"}},
                ],
            },
        },
    )

    result = RobotDriver().execute(step)

    assert result.ok
    assert result.payload["binding"]["action"] == "device.centrifuge.filter.run"
    assert result.payload["projection"]["semantic_args"]["program"] == (
        "centrifugal_filtration_program(membrane=silica, drive=8000g, duration=1min)"
    )
