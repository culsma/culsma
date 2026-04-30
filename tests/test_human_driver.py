from __future__ import annotations

from culsma.driver.human import HumanDriver
from culsma.driver.human_driver.run_sheet import build_run_sheet
from culsma.pipeline.plan_nodes import PlanStep


def test_human_driver_emits_structured_mutation_instruction_payload():
    step = PlanStep(
        step_id="step.mut.1",
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

    result = HumanDriver().execute(step)

    assert result.ok
    assert result.code == "DRV_HUMAN_OK"
    assert result.payload["driver_kind"] == "human"
    assert result.payload["instruction"]["title"] == "Pipette Transfer Step"
    assert "Using P20 single-channel pipette" in result.payload["instruction"]["summary"]
    assert result.payload["instruction_packet"]["section"]["title"] == "Material Transfer"
    assert result.payload["instruction_packet"]["item"]["step_id"] == "step.mut.1"
    assert result.payload["binding"]["strategy_kind"] == "pipette_transfer"
    assert result.payload["binding"]["pipette_label"] == "P20 single-channel pipette"
    assert result.payload["binding"]["tip_label"] == "filtered clear tip"
    assert any("Handle gently" in line for line in result.payload["instruction"]["details"])


def test_human_driver_preserves_stub_payload_for_observation_results():
    step = PlanStep(
        step_id="step.obs.1",
        op="phy",
        args={
            "sample": {"kind": "IRIdentifier", "name": "detector_surface"},
            "quantity": {"kind": "IRIdentifier", "name": "current"},
        },
    )

    result = HumanDriver(
        op_payloads={
            "phy": {
                "result": {
                    "current_pulse": 12.5,
                }
            }
        }
    ).execute(step)

    assert result.ok
    assert result.payload["driver_kind"] == "human"
    assert result.payload["result"]["current_pulse"] == 12.5
    assert result.payload["instruction"]["category"] == "observation"


def test_human_driver_prefers_program_kind_specific_tool_binding():
    step = PlanStep(
        step_id="step.obs.2",
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

    result = HumanDriver().execute(step)

    assert result.ok
    assert result.payload["binding"]["program_kind"] == "temperature_program"
    assert result.payload["binding"]["tool_label"] == "temperature probe workflow"


def test_human_driver_uses_p200_strategy_for_mid_volume_mutation():
    step = PlanStep(
        step_id="step.mut.2",
        op="Mutation",
        args={
            "target": {"kind": "IRIdentifier", "name": "dst"},
            "sources": [
                {
                    "kind": "IRPair",
                    "left": {"kind": "IRIdentifier", "name": "src"},
                    "right": {"kind": "IRQuantity", "value": 150, "unit": "uL"},
                }
            ],
        },
    )

    result = HumanDriver().execute(step)

    assert result.ok
    assert result.payload["binding"]["pipette_label"] == "P200 single-channel pipette"
    assert result.payload["binding"]["tip_label"] == "filtered yellow tip"


def test_human_run_sheet_groups_projections_by_category_in_order():
    driver = HumanDriver()
    sheet = build_run_sheet(
        [
            driver.project_step(
                PlanStep(
                    step_id="step.setup.1",
                    op="AllocContainer",
                    args={"kind": {"kind": "IRIdentifier", "name": "tube"}},
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.mut.3",
                    op="Mutation",
                    args={
                        "target": {"kind": "IRIdentifier", "name": "dst"},
                        "sources": [
                            {
                                "kind": "IRPair",
                                "left": {"kind": "IRIdentifier", "name": "src"},
                                "right": {"kind": "IRQuantity", "value": 10, "unit": "uL"},
                            }
                        ],
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.obs.3",
                    op="phy",
                    args={"sample": {"kind": "IRIdentifier", "name": "probe"}},
                )
            ),
        ]
    )

    assert [item.title for item in sheet.items] == ["Container Preparation", "Pipette Transfer Step", "Observation Step"]
    assert sheet.items[1].step_ids == ("step.mut.3",)
    assert sheet.items[2].title == "Observation Step"
    assert sheet.sections == ()


def test_human_run_sheet_hides_internal_setup_and_merges_repeated_steps():
    driver = HumanDriver()
    sheet = build_run_sheet(
        [
            driver.project_step(
                PlanStep(
                    step_id="step.setup.define",
                    op="DefineContent",
                    args={"code": {"kind": "IRString", "value": "INC01"}},
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.setup.load",
                    op="LoadContent",
                    args={
                        "amount": {"kind": "IRQuantity", "value": 200, "unit": "uL"},
                        "content": {"kind": "IRIdentifier", "name": "INC01"},
                        "container": {"kind": "IRIdentifier", "name": "sample_tube"},
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.mut.4",
                    op="Mutation",
                    args={
                        "target": {"kind": "IRIdentifier", "name": "dst"},
                        "sources": [
                            {
                                "kind": "IRPair",
                                "left": {"kind": "IRIdentifier", "name": "src"},
                                "right": {"kind": "IRQuantity", "value": 10, "unit": "uL"},
                            }
                        ],
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.mut.5",
                    op="Mutation",
                    args={
                        "target": {"kind": "IRIdentifier", "name": "dst"},
                        "sources": [
                            {
                                "kind": "IRPair",
                                "left": {"kind": "IRIdentifier", "name": "src"},
                                "right": {"kind": "IRQuantity", "value": 10, "unit": "uL"},
                            }
                        ],
                    },
                )
            ),
        ]
    )

    assert sheet.items[0].summary == "Load 200uL of INC01 into sample_tube."
    assert len(sheet.items) == 2
    assert sheet.items[1].repeat_count == 2
    assert sheet.items[1].summary.startswith("Repeat 2 times:")


def test_human_run_sheet_preserves_original_execution_order_across_repeated_categories():
    driver = HumanDriver()
    sheet = build_run_sheet(
        [
            driver.project_step(
                PlanStep(
                    step_id="step.setup.1",
                    op="AllocContainer",
                    args={
                        "bind": {"kind": "IRIdentifier", "name": "sample_tube"},
                        "label": {"kind": "IRString", "value": "Sample"},
                        "kind": {"kind": "IRIdentifier", "name": "tube"},
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.mut.1",
                    op="Mutation",
                    args={
                        "target": {"kind": "IRIdentifier", "name": "sample_tube"},
                        "sources": [
                            {
                                "kind": "IRPair",
                                "left": {"kind": "IRIdentifier", "name": "feed_stock"},
                                "right": {"kind": "IRQuantity", "value": 10, "unit": "uL"},
                            }
                        ],
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.sep.1",
                    op="sep",
                    args={"sample": {"kind": "IRIdentifier", "name": "sample_tube"}},
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.obs.1",
                    op="img",
                    args={
                        "sample": {"kind": "IRIdentifier", "name": "sample_tube"},
                        "quantity": {"kind": "IRIdentifier", "name": "fluorescence"},
                    },
                )
            ),
            driver.project_step(
                PlanStep(
                    step_id="step.mut.2",
                    op="Mutation",
                    args={
                        "target": {"kind": "IRIdentifier", "name": "sample_tube"},
                        "sources": [
                            {
                                "kind": "IRPair",
                                "left": {"kind": "IRIdentifier", "name": "feed_stock"},
                                "right": {"kind": "IRQuantity", "value": 5, "unit": "uL"},
                            }
                        ],
                    },
                )
            ),
        ]
    )

    assert [item.title for item in sheet.items] == [
        "Container Preparation",
        "Pipette Transfer Step",
        "Separation Step",
        "Observation Step",
        "Pipette Transfer Step",
    ]
    assert sheet.items[-1].step_ids == ("step.mut.2",)
