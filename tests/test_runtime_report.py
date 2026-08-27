from __future__ import annotations

from culsma.runtime.report import (
    LAB_REPORT_SCHEMA,
    ContainerKindCount,
    ContainerResourceSummary,
    ExecutionSummary,
    FinalProductRow,
    InputInventoryRow,
    IntermediateMaterialRow,
    InstrumentSummary,
    LabReport,
    MaterialsReport,
    NamedCount,
    ProcessSummary,
    QcResult,
    ReagentConsumptionRow,
    ResourceSummary,
)


def test_lab_report_serializes_complete_model_to_stable_json_contract():
    report = LabReport(
        execution=ExecutionSummary(
            ok=True,
            diagnostic_count=1,
            total_steps=4,
            completed_steps=3,
            failed_steps=0,
            skipped_steps=1,
        ),
        headline="Completed.",
        materials=MaterialsReport(
            has_material_state=True,
            input_inventory=[
                InputInventoryRow(name="Input", initial_uL=20.0, initial_mL=0.02, initial_mg=0.0)
            ],
            final_products=[
                FinalProductRow(
                    name="Product",
                    volume_uL=10.0,
                    volume_mL=0.01,
                    mass_mg=2.0,
                    primary_component="DNA",
                )
            ],
            intermediate_materials=[
                IntermediateMaterialRow(
                    name="Intermediate",
                    final_uL=5.0,
                    final_mL=0.005,
                    mass_mg=None,
                    primary_component=None,
                )
            ],
            reagent_consumption=[
                ReagentConsumptionRow(
                    name="Reagent",
                    roles=["source"],
                    consumed_uL=None,
                    consumed_mL=None,
                    consumed_mg=2.0,
                )
            ],
        ),
        qc_results=[QcResult(item="QC", values={"item": "ignored", "ct_estimate": 19.4})],
        resource_summary=ResourceSummary(
            containers=ContainerResourceSummary(
                allocated_count=2,
                touched_count=1,
                container_kinds=[ContainerKindCount(kind="tube", count=2)],
                touched_names=["Product"],
            ),
            instruments=InstrumentSummary(
                tools=[NamedCount(name="pipette", count=1)],
                devices=[NamedCount(name="cycler", count=1)],
            ),
        ),
        process_summary=ProcessSummary(
            mutation_steps=1,
            separation_steps=1,
            environment_steps=1,
            readout_steps=1,
        ),
        alerts=["WARN: review"],
    )

    assert report.to_dict() == {
        "schema": LAB_REPORT_SCHEMA,
        "execution": {
            "ok": True,
            "diagnostic_count": 1,
            "total_steps": 4,
            "completed_steps": 3,
            "failed_steps": 0,
            "skipped_steps": 1,
        },
        "headline": "Completed.",
        "materials": {
            "has_material_state": True,
            "input_inventory": [
                {"name": "Input", "initial_uL": 20.0, "initial_mL": 0.02, "initial_mg": 0.0}
            ],
            "final_products": [
                {
                    "name": "Product",
                    "volume_uL": 10.0,
                    "volume_mL": 0.01,
                    "mass_mg": 2.0,
                    "primary_component": "DNA",
                }
            ],
            "intermediate_materials": [
                {
                    "name": "Intermediate",
                    "final_uL": 5.0,
                    "final_mL": 0.005,
                    "mass_mg": None,
                    "primary_component": None,
                }
            ],
            "reagent_consumption": [
                {
                    "name": "Reagent",
                    "roles": ["source"],
                    "consumed_uL": None,
                    "consumed_mL": None,
                    "consumed_mg": 2.0,
                }
            ],
        },
        "qc_results": [{"item": "QC", "ct_estimate": 19.4}],
        "resource_summary": {
            "containers": {
                "allocated_count": 2,
                "touched_count": 1,
                "container_kinds": [{"kind": "tube", "count": 2}],
                "touched_names": ["Product"],
            },
            "instruments": {
                "tools": [{"name": "pipette", "count": 1}],
                "devices": [{"name": "cycler", "count": 1}],
            },
        },
        "process_summary": {
            "mutation_steps": 1,
            "separation_steps": 1,
            "environment_steps": 1,
            "readout_steps": 1,
        },
        "alerts": ["WARN: review"],
        "external_inventory": {
            "schema": "culsma_inventory_reconciliation_v1",
            "checked": False,
            "sufficient": None,
            "reason": "inventory_not_supplied",
            "items": [],
            "shortages": [],
        },
    }
