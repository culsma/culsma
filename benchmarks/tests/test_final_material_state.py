"""Final-state extraction tests; no language parser or CLI execution required."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from benchmark_metrics import EvidenceError, final_material_records


def run_with(containers):
    return {"ok": True, "state": {"artifacts": {"material_state": {"containers": containers}}}}


class FinalMaterialStateTests(unittest.TestCase):
    def test_residual_stocks_and_duplicate_labels_keep_identity_and_raw_state(self):
        raw = {"volume_uL": 24000, "metadata": {"label": "WashBuffer"}}
        run = run_with({"container/a~1": raw, "container/b": deepcopy(raw)})
        before = deepcopy(run)
        rows = final_material_records(run)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["record"]["volume_uL"], 24000)
        self.assertEqual(run, before)
        for row in rows:
            value = run
            for token in row["evidence"]["json_pointer"].split("/")[1:]:
                value = value[token.replace("~1", "/").replace("~0", "~")]
            self.assertEqual(value, row["record"]["material_state"])

    def test_empty_and_fraction_handles_excluded_but_zero_volume_cells_kept(self):
        rows = final_material_records(run_with({
            "empty": {"volume_uL": 0, "mass_mg": 0},
            "source::fraction0": {"volume_uL": 20},
            "cells": {"volume_uL": 0, "component_quantities": {
                "cells": {"dimension": "count", "unit": "cells", "value": 100}}},
            "mass": {"volume_uL": 0, "mass_mg": 2},
        }))
        self.assertEqual([r["container_id"] for r in rows], ["cells", "mass"])

    def test_uses_final_state_not_historical_snapshots(self):
        run = run_with({"stock": {"volume_uL": 0}})
        run["events"] = [{"payload": {"material_state_snapshot": {
            "containers": {"stock": {"volume_uL": 100}}}}}]
        self.assertEqual(final_material_records(run), [])

    def test_missing_state_and_failed_run_rejected(self):
        for run in ({"ok": True}, {**run_with({}), "ok": False}):
            with self.assertRaises(EvidenceError):
                final_material_records(run)

    def test_invalid_quantities_rejected(self):
        for raw in ({}, {"volume_uL": float("nan")}, {"volume_uL": -10},
                    {"volume_uL": "10"}, {"component_quantities": {"x": {}}}):
            with self.assertRaises(EvidenceError):
                final_material_records(run_with({"bad": raw}))


if __name__ == "__main__":
    unittest.main()
