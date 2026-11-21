"""Versioned results use one program tree and retain verifiable provenance."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
RUNNER = runpy.run_path(str(ROOT / "benchmarks/evaluate.py"))


def test_changed_input_rejected(tmp_path):
    case = tmp_path / "modules/example"
    case.mkdir(parents=True)
    program = case / "protocol.culs"
    program.write_text("return tube();")
    manifest = {"artifacts": [{"path": "modules/example"}],
                "input_sha256": {"modules/example/protocol.culs": "0" * 64}}
    with pytest.raises(ValueError, match="Input changed"):
        RUNNER["verify_inputs"](tmp_path, manifest)


def test_unrecorded_program_rejected(tmp_path):
    case = tmp_path / "modules/example"
    case.mkdir(parents=True)
    (case / "protocol.culs").write_text("return tube();")
    manifest = {"artifacts": [{"path": "modules/example"}], "input_sha256": {}}
    with pytest.raises(ValueError, match="inventory changed"):
        RUNNER["verify_inputs"](tmp_path, manifest)


@pytest.mark.parametrize("version,matched", [("1.0.7", 172), ("1.0.9", 173), ("1.0.11", 173)])
def test_evaluation_records_are_reproducible_without_program_copies(version, matched):
    folder = ROOT / "benchmarks/evaluations" / version
    manifest = json.loads((folder / "manifest.json").read_text())
    summary = json.loads((folder / "summary.json").read_text())
    assert not list(folder.rglob("*.culs"))
    assert not list(folder.rglob("source.md"))
    assert summary["all_software_pass"]
    assert summary["rules"] == "modular-source-step-correspondence-v2"
    assert summary["groups"]["original"] == {"matched_steps": matched, "total_steps": 173}
    assert summary["groups"]["external"] == {"matched_steps": 21, "total_steps": 21}
    assert summary["manifest_sha256"] == RUNNER["digest"](folder / "manifest.json")
    assert summary["runtime_commit"] == manifest["runtime_commit"]
    assert summary["input_sha256"] == manifest["input_sha256"]
    for name, expected in summary["output_sha256"].items():
        assert RUNNER["digest"](folder / name) == expected
    for name, expected in summary["runner_sha256"].items():
        assert RUNNER["digest"](ROOT / "benchmarks" / name) == expected
    if manifest["benchmark_commit"]:
        paths = ["benchmarks/" + name for name in manifest["input_sha256"]]
        files = RUNNER["git_files"](manifest["benchmark_commit"], paths)
        for name, expected in manifest["input_sha256"].items():
            assert hashlib.sha256(files["benchmarks/" + name]).hexdigest() == expected
    else:
        RUNNER["verify_inputs"](ROOT / "benchmarks", manifest)
    for row in summary["artifacts"]:
        assert row["coverage"]["rules"] == summary["rules"]
        assert row["event_replay_equal"]
        assert row["execution"]["completed_steps"] == row["execution"]["total_steps"]


def test_later_versions_evaluate_identical_program_inputs():
    manifests = [json.loads((ROOT / "benchmarks/evaluations" / v / "manifest.json").read_text())
                 for v in ("1.0.9", "1.0.11")]
    assert manifests[0]["input_sha256"] == manifests[1]["input_sha256"]
