from __future__ import annotations

from copy import deepcopy

import pytest

from culsma.runtime.inventory import reconcile_external_inventory


def _report(*, ok: bool = True) -> dict:
    return {
        "schema": "lab_report_v1",
        "execution": {"ok": ok},
        "materials": {
            "reagent_consumption": [
                {
                    "name": "CellStock",
                    "consumed_uL": 80.0,
                    "consumed_mg": None,
                    "consumed_cells": 100000.0,
                },
                {
                    "name": "BufferStock",
                    "consumed_uL": 50.0,
                    "consumed_mg": None,
                },
            ]
        },
    }


def test_inventory_reconciliation_reports_shortage_without_mutating_inputs():
    report = _report()
    snapshot = {
        "schema": "culsma_inventory_snapshot_v1",
        "items": [
            {
                "name": "CellStock",
                "available": {"volume_uL": 100.0, "count_cells": 90000.0},
            },
            {"name": "BufferStock", "available": {"volume_uL": 75.0}},
        ],
    }
    original_report = deepcopy(report)
    original_snapshot = deepcopy(snapshot)

    reconciled = reconcile_external_inventory(report=report, snapshot=snapshot)

    assert report == original_report
    assert snapshot == original_snapshot
    result = reconciled["external_inventory"]
    assert result["checked"] is True
    assert result["sufficient"] is False
    assert result["shortages"] == [
        {
            "name": "CellStock",
            "shortage": {"volume_uL": 0.0, "mass_mg": None, "count_cells": 10000.0},
        }
    ]
    cell_stock = result["items"][0]
    assert cell_stock["required"] == {
        "volume_uL": 80.0,
        "mass_mg": None,
        "count_cells": 100000.0,
    }
    assert cell_stock["available"] == {
        "volume_uL": 100.0,
        "mass_mg": None,
        "count_cells": 90000.0,
    }
    assert cell_stock["remaining"] == {
        "volume_uL": 20.0,
        "mass_mg": None,
        "count_cells": 0.0,
    }


def test_inventory_reconciliation_keeps_runtime_failure_separate():
    reconciled = reconcile_external_inventory(
        report=_report(ok=False),
        snapshot={"schema": "culsma_inventory_snapshot_v1", "items": []},
    )

    assert reconciled["execution"]["ok"] is False
    assert reconciled["external_inventory"] == {
        "schema": "culsma_inventory_reconciliation_v1",
        "checked": False,
        "sufficient": None,
        "reason": "runtime_incomplete",
        "items": [],
        "shortages": [],
    }


def test_inventory_reconciliation_rejects_negative_availability():
    with pytest.raises(ValueError, match="must be non-negative"):
        reconcile_external_inventory(
            report=_report(),
            snapshot={
                "schema": "culsma_inventory_snapshot_v1",
                "items": [
                    {"name": "CellStock", "available": {"count_cells": -1.0}}
                ],
            },
        )
