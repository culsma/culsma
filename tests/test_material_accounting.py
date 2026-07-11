from __future__ import annotations

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.accounting import MaterialAccountingRecorder
from culsma.runtime.material.result import MaterialMovementSpec, MaterialUpdateResult


def _container(volume_uL: float, *, label: str = "Stock") -> dict:
    return {
        "volume_uL": volume_uL,
        "mass_mg": 0.0,
        "components": {},
        "metadata": {"label": label},
    }


def test_accounting_combines_initial_and_loaded_lots_in_one_container():
    recorder = MaterialAccountingRecorder()
    initial_state = {"containers": {"stock": _container(10.0)}}
    accounting = recorder.initialize(initial_state)

    loaded_state = {"containers": {"stock": _container(20.0)}}
    recorder.record(
        step=PlanStep(step_id="load", op="LoadContent"),
        result=MaterialUpdateResult(
            material_state=loaded_state,
            delta={
                "op": "LoadContent",
                "container": "stock",
                "content_id": "buffer",
                "amount": 10.0,
                "unit": "uL",
            },
        ),
        accounting=accounting,
    )

    moved_state = {
        "containers": {
            "stock": _container(10.0),
            "reactor": _container(10.0, label="Reactor"),
        }
    }
    recorder.record(
        step=PlanStep(step_id="move", op="Mutation"),
        result=MaterialUpdateResult(
            material_state=moved_state,
            delta={"op": "Mutation"},
            movements=[
                MaterialMovementSpec(source="stock", destination="reactor", volume_uL=10.0)
            ],
        ),
        accounting=accounting,
    )

    lots = accounting.list_input_lots()
    assert [(lot.origin, lot.name, lot.initial.volume_uL) for lot in lots] == [
        ("initial_state", "Stock", 10.0),
        ("load_content", "Stock", 10.0),
    ]
    consumed = accounting.consumption_by_input()
    assert consumed["initial:stock"].volume_uL == 5.0
    assert consumed["load:load:stock"].volume_uL == 5.0
    reactor = accounting.container_allocation("reactor")
    assert reactor["initial:stock"].volume_uL == 5.0
    assert reactor["load:load:stock"].volume_uL == 5.0


def test_accounting_uses_explicit_multi_source_multi_target_movements():
    recorder = MaterialAccountingRecorder()
    before = {
        "containers": {
            "sample": _container(60.0, label="Sample"),
            "buffer": _container(40.0, label="Buffer"),
            "output_x": _container(0.0, label="Output X"),
            "output_y": _container(0.0, label="Output Y"),
        }
    }
    accounting = recorder.initialize(before)
    after = {
        "containers": {
            "sample": _container(0.0, label="Sample"),
            "buffer": _container(0.0, label="Buffer"),
            "output_x": _container(70.0, label="Output X"),
            "output_y": _container(30.0, label="Output Y"),
        }
    }

    recorder.record(
        step=PlanStep(step_id="route", op="CustomMaterialOperation"),
        result=MaterialUpdateResult(
            material_state=after,
            delta={"op": "CustomMaterialOperation"},
            movements=[
                MaterialMovementSpec(source="sample", destination="output_x", volume_uL=60.0),
                MaterialMovementSpec(source="buffer", destination="output_x", volume_uL=10.0),
                MaterialMovementSpec(source="buffer", destination="output_y", volume_uL=30.0),
            ],
        ),
        accounting=accounting,
    )

    output_x = accounting.container_allocation("output_x")
    output_y = accounting.container_allocation("output_y")
    assert output_x["initial:sample"].volume_uL == 60.0
    assert output_x["initial:buffer"].volume_uL == 10.0
    assert "initial:sample" not in output_y
    assert output_y["initial:buffer"].volume_uL == 30.0


def test_accounting_does_not_guess_ambiguous_multi_to_multi_state_delta():
    recorder = MaterialAccountingRecorder()
    before = {
        "containers": {
            "source_a": _container(60.0, label="Source A"),
            "source_b": _container(40.0, label="Source B"),
        }
    }
    accounting = recorder.initialize(before)
    after = {
        "containers": {
            "source_a": _container(0.0, label="Source A"),
            "source_b": _container(0.0, label="Source B"),
            "target_x": _container(70.0, label="Target X"),
            "target_y": _container(30.0, label="Target Y"),
        }
    }

    recorder.record(
        step=PlanStep(step_id="ambiguous", op="CustomMaterialOperation"),
        result=MaterialUpdateResult(material_state=after, delta={"op": "CustomMaterialOperation"}),
        accounting=accounting,
    )

    assert accounting.movements == []
    assert accounting.consumption_by_input() == {}
