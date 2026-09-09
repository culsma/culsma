import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reproduce", ROOT / "reproduce.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReproductionTests(unittest.TestCase):
    def test_all_frozen_records_reproduce_manuscript_counts(self):
        rows = r.derive(ROOT / "expected/runtime")
        expected = r.read_json(ROOT / "expected/tables.json")
        self.assertEqual(rows, expected["cases"])
        self.assertEqual(r.total(rows), expected["totals"])
        self.assertEqual(r.compare(rows, ROOT / "expected/runtime"), [])

    def test_worked_example_never_enters_totals(self):
        rows = {"00": dict.fromkeys(r.FIELDS, 999), "01": dict.fromkeys(r.FIELDS, 1)}
        self.assertEqual(r.total(rows), dict.fromkeys(r.FIELDS, 1))

    def test_annotation_rows_not_cached_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            r.write_json(dest / "source.steps.json", {"steps": [{"id": "S1"}, {"id": "S2"}]})
            r.write_json(dest / "action_descriptors.json", {
                "descriptor_item_count": 999,
                "rows": [{"step": "S1", "descriptors": ["temperature and time"]},
                         {"step": "S2", "descriptors": ["readout"]}]})
            r.write_json(dest / "object_reuse.json", {
                "tracked_object_count": 999, "reuse_link_count": 999,
                "rows": [{"object": "treated / reference", "introduced_at": "S1", "used_in": ["S2"]}]})
            counts = r.annotation_counts(dest)
            self.assertEqual(counts, dict(source_steps=2, descriptor_items=2, reused_objects=1, later_use_links=1))

    def test_invalid_reuse_link_is_not_silently_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in ("source.steps.json", "action_descriptors.json", "object_reuse.json"):
                r.write_json(dest / name, r.read_json(ROOT / "worked-example/00" / name))
            obj = r.read_json(dest / "object_reuse.json")
            obj["rows"][0]["used_in"].append(obj["rows"][0]["introduced_at"])
            r.write_json(dest / "object_reuse.json", obj)
            with self.assertRaises(ValueError):
                r.annotation_counts(dest)

    def test_completed_versus_total_excludes_skipped(self):
        output = r.read_json(ROOT / "expected/runtime/01/output.json.gz")
        self.assertEqual(r.runtime_counts(output)["active_steps"], 611)
        self.assertEqual(output["report"]["execution"]["total_steps"], 657)

    def test_failed_or_incomplete_execution_rejected(self):
        original = r.read_json(ROOT / "expected/runtime/00/output.json.gz")
        for field, value in (("diagnostic_count", 1), ("failed_steps", 1), ("completed_steps", 0)):
            output = copy.deepcopy(original)
            output["report"]["execution"][field] = value
            with self.assertRaises(ValueError):
                r.runtime_counts(output)

    def test_duplicate_display_names_are_distinct_records(self):
        output = r.read_json(ROOT / "expected/runtime/01/output.json.gz")
        names = output["report"]["resource_summary"]["containers"]["touched_names"]
        self.assertGreater(len(names), len(set(names)))
        self.assertEqual(r.runtime_counts(output)["touched_containers"], len(names))

    def test_quantity_change_detected_even_with_same_counts(self):
        original = r.read_json(ROOT / "expected/runtime/00/output.json.gz")
        changed = copy.deepcopy(original)
        changed["report"]["materials"]["final_products"][0]["volume_uL"] += 1
        self.assertEqual(r.runtime_counts(original), r.runtime_counts(changed))
        self.assertNotEqual(r.record_projection(original), r.record_projection(changed))

    def test_missing_runtime_field_fails(self):
        output = r.read_json(ROOT / "expected/runtime/00/output.json.gz")
        del output["report"]["materials"]["final_products"]
        with self.assertRaises(KeyError):
            r.runtime_counts(output)

    def test_changed_descriptor_causes_count_difference(self):
        rows = r.derive(ROOT / "expected/runtime")
        rows["01"]["descriptor_items"] += 1
        differences = r.compare(rows, ROOT / "expected/runtime")
        self.assertTrue(any("Case 01 descriptor_items" in d for d in differences))

    def test_checksum_detects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "input.txt").write_text("original")
            r.write_json(dest / "checksums.json", {"input.txt": r.sha256(dest / "input.txt")})
            with patch.object(r, "ROOT", dest):
                r.check_files()
                (dest / "input.txt").write_text("changed")
                with self.assertRaises(ValueError):
                    r.check_files()

    def test_supported_python_patch_versions_are_accepted(self):
        for version in ("3.11.11", "3.12.8", "3.12.11", "3.13.1"):
            with self.subTest(version=version), patch.object(r.platform, "python_version", return_value=version), \
                 patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.6", "lark": "1.3.1"}[n]):
                self.assertEqual(r.check_environment()["python"], version)

    def test_unverified_python_series_are_rejected(self):
        for version in ("3.10.16", "3.14.0"):
            with self.subTest(version=version), patch.object(r.platform, "python_version", return_value=version), \
                 patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.6", "lark": "1.3.1"}[n]):
                with self.assertRaisesRegex(ValueError, "unsupported Python"):
                    r.check_environment()

    def test_python_prerelease_is_rejected(self):
        from types import SimpleNamespace
        with patch.object(r.platform, "python_version", return_value="3.13.0rc1"), \
             patch.object(r.sys, "version_info", SimpleNamespace(releaselevel="candidate")), \
             patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.6", "lark": "1.3.1"}[n]):
            with self.assertRaisesRegex(ValueError, "unsupported Python"):
                r.check_environment()

    def test_dependencies_still_require_exact_versions(self):
        for versions in ({"culsma": "1.0.5", "lark": "1.3.1"}, {"culsma": "1.0.6", "lark": "1.2.2"}):
            with self.subTest(versions=versions), patch.object(r.platform, "python_version", return_value="3.13.1"), \
                 patch.object(r.importlib.metadata, "version", side_effect=versions.__getitem__):
                with self.assertRaisesRegex(ValueError, "package version mismatch"):
                    r.check_environment()

    def test_real_snapshot_integrity(self):
        r.check_files()


if __name__ == "__main__":
    unittest.main()
