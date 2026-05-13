from __future__ import annotations

import json
import sys
from pathlib import Path

from culsma.cli import main


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_INPUT = ROOT / "examples" / "minimal" / "public_minimal.culs"


def test_cli_run_prints_human_summary_to_stdout_by_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(MINIMAL_INPUT)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("PublicMinimal ok")
    assert "return:" in captured.out
    assert "Target (tube)" in captured.out
    assert "volume: 5 uL" in captured.out
    assert captured.err == ""


def test_cli_run_prints_machine_output_json_when_requested(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(MINIMAL_INPUT), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "culsma_run_output_v1"
    assert payload["report"]["schema"] == "lab_report_v1"
    assert payload["returns"]["PublicMinimal"]["value"]["id"] == "Target"
    assert captured.err == ""


def test_cli_accepts_top_level_input_path_shorthand(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", str(MINIMAL_INPUT)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("PublicMinimal ok")
    assert "Target (tube)" in captured.out
    assert captured.err == ""


def test_cli_human_summary_includes_returned_container_state(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(MINIMAL_INPUT)])

    main()

    captured = capsys.readouterr()
    assert captured.out == (
        "PublicMinimal ok\n"
        "\n"
        "return:\n"
        "  Target (tube)\n"
        "    volume: 5 uL\n"
        "    mass: 5 mg\n"
        "\n"
        "execution: 5/5 steps completed, 0 diagnostics\n"
    )


def test_cli_human_summary_includes_scalar_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "scalar_return.culs"
    source.write_text('protocol ScalarReturn { return "ready"; }\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("ScalarReturn ok")
    assert "return:\n  ready" in captured.out


def test_cli_human_summary_includes_quantity_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "quantity_return.culs"
    source.write_text("protocol QuantityReturn { return 12uL; }\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("QuantityReturn ok")
    assert "return:\n  12 uL" in captured.out


def test_cli_human_summary_includes_list_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "list_return.culs"
    source.write_text('protocol ListReturn { return ["alpha", 2, 3uL]; }\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("ListReturn ok")
    assert "return:\n  [" in captured.out
    assert "alpha," in captured.out
    assert "2," in captured.out
    assert "3 uL," in captured.out


def test_cli_human_summary_includes_named_multi_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "named_return.culs"
    source.write_text(
        'protocol NamedReturn returns (status, volume) { return status = "ready", volume = 7uL; }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("NamedReturn ok")
    assert "return:" in captured.out
    assert "status:\n    ready" in captured.out
    assert "volume:\n    7 uL" in captured.out


def test_cli_machine_output_preserves_return_value_types(tmp_path, monkeypatch, capsys):
    source = tmp_path / "typed_return.culs"
    source.write_text(
        'protocol TypedReturn returns (label, volume, items) { return label = "ready", volume = 9uL, items = ["x", 2]; }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    returns = payload["returns"]["TypedReturn"]["bindings"]
    assert returns["label"] == "ready"
    assert returns["volume"] == {"kind": "IRQuantity", "unit": "uL", "value": 9.0}
    assert returns["items"] == ["x", 2]
    assert payload["report"]["schema"] == "lab_report_v1"


def test_cli_run_writes_primary_result_when_output_is_requested(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(MINIMAL_INPUT), "--json"])

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
    assert payload["schema"] == "culsma_run_output_v1"
    assert payload["report"]["schema"] == "lab_report_v1"
    assert captured.out == ""
    assert captured.err == ""


def test_cli_run_writes_debug_artifacts_only_when_requested(tmp_path, monkeypatch, capsys):
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(MINIMAL_INPUT), "--json", "--artifacts-dir", str(artifacts_dir)],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "culsma_run_output_v1"
    assert payload["report"]["schema"] == "lab_report_v1"
    assert payload["returns"]["PublicMinimal"]["value"]["id"] == "Target"
    assert captured.err == ""
    expected = {
        "summary.json",
        "ast.json",
        "ir.json",
        "validate.json",
        "typecheck.json",
        "plan.json",
        "run.json",
        "output.json",
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
