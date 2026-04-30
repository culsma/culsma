from __future__ import annotations

import json
import sys
from pathlib import Path

from culsma.cli import main


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_INPUT = ROOT / "examples" / "minimal" / "public_minimal.culs"


def test_cli_run_prints_primary_result_to_stdout_by_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(MINIMAL_INPUT)])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "lab_report_v1"
    assert "execution" in payload
    assert captured.err == ""


def test_cli_run_writes_primary_result_when_output_is_requested(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(MINIMAL_INPUT)])

    main()

    stdout_payload = json.loads(capsys.readouterr().out)
    output_path = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(MINIMAL_INPUT), "--output", str(output_path)],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == stdout_payload
    assert captured.out == ""
    assert captured.err == ""


def test_cli_run_writes_debug_artifacts_only_when_requested(tmp_path, monkeypatch, capsys):
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(MINIMAL_INPUT), "--artifacts-dir", str(artifacts_dir)],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "lab_report_v1"
    assert captured.err == ""
    expected = {
        "summary.json",
        "ast.json",
        "ir.json",
        "validate.json",
        "typecheck.json",
        "plan.json",
        "run.json",
        "result.json",
    }
    assert {path.name for path in artifacts_dir.iterdir()} == expected


def test_cli_replay_reconstructs_state_from_explicit_run_artifact(tmp_path, monkeypatch, capsys):
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(MINIMAL_INPUT), "--artifacts-dir", str(artifacts_dir)],
    )
    main()
    capsys.readouterr()

    replay_path = tmp_path / "replayed_state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "culsma",
            "replay",
            "--run-json",
            str(artifacts_dir / "run.json"),
            "--out",
            str(replay_path),
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    replayed = json.loads(replay_path.read_text(encoding="utf-8"))
    assert payload["event_count"] > 0
    assert payload["step_count"] > 0
    assert "step_status" in replayed
