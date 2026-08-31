from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from culsma.cli import execute_batch_pipeline
from culsma.cli import execute_pipeline
from culsma.cli import main


SMOKE_SOURCE = """\
protocol CliSmoke {
  let sample = tube(label = "AcquisitionSample", capacity = 2000uL, load = [content(kind = "biosample", code = "S1", type = "cell_sample"):1000uL]);
  return sample;
}
"""


def _write_smoke_source(tmp_path: Path) -> Path:
    source = tmp_path / "cli_smoke.culs"
    source.write_text(SMOKE_SOURCE, encoding="utf-8")
    return source


def _container_by_label(containers: dict, label: str) -> dict:
    matches = [
        raw
        for raw in containers.values()
        if isinstance(raw, dict)
        and isinstance(raw.get("metadata"), dict)
        and raw["metadata"].get("label") == label
    ]
    assert len(matches) == 1
    return matches[0]


def test_cli_run_prints_human_summary_to_stdout_by_default(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("CliSmoke ok")
    assert "return:" in captured.out
    assert "AcquisitionSample (tube)" in captured.out
    assert "volume: 1000 uL" in captured.out
    assert captured.err == ""


def test_cli_run_prints_machine_output_json_when_requested(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "culsma_run_output_v1"
    assert payload["report"]["schema"] == "lab_report_v1"
    returned = payload["returns"]["CliSmoke"]["value"]
    assert returned["id"] == "container/cli_smoke.CliSmoke/p0.s0%3A%3Aalloc/sample"
    assert returned["label"] == "AcquisitionSample"
    assert captured.err == ""


def test_cli_rejects_removed_protocol_entry_option(tmp_path, monkeypatch, capsys):
    source = tmp_path / "multi_root.culs"
    source.write_text("protocol Wrapper {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--entry-protocol", "Wrapper", "--json"])

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unrecognized arguments: --entry-protocol" in captured.err


def test_cli_accepts_legacy_value_less_inventory_check_option(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--inventory-check"])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("CliSmoke ok")
    assert captured.err == ""


def test_execute_pipeline_never_synthesizes_insufficient_source_material(tmp_path):
    source = tmp_path / "insufficient_source.culs"
    source.write_text(
        """
protocol InsufficientSource returns (target) {
  let source = tube(
    label = "VolumeSource",
    capacity = 100uL,
    load = [content(kind = formulation, type = buffer, code = "BUFFER"):10uL]
  );
  let target = tube(label = "VolumeTarget", capacity = 100uL);
  target << [source:20uL];
  return target = target;
}
""",
        encoding="utf-8",
    )

    bundle = execute_pipeline([source])

    assert not bundle["output"]["ok"]
    assert "MAT_INSUFFICIENT_VOLUME" in [
        diagnostic["code"] for diagnostic in bundle["run"]["diagnostics"]
    ]
    containers = bundle["run"]["state"]["artifacts"]["material_state"]["containers"]
    assert _container_by_label(containers, "VolumeSource")["volume_uL"] == 10.0
    assert _container_by_label(containers, "VolumeTarget")["volume_uL"] == 0.0


def test_cli_adds_external_inventory_shortage_to_final_result_without_failing_runtime(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "inventory_result.culs"
    source.write_text(
        """
protocol InventoryResult {
  let stock = tube(
    label = "Stock",
    capacity = 100uL,
    load = [content(kind = formulation, type = buffer, code = "BUFFER"):10uL]
  );
  let target = tube(label = "Target", capacity = 100uL);
  target << [stock:5uL];
}
""",
        encoding="utf-8",
    )
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "culsma_inventory_snapshot_v1",
                "items": [{"name": "Stock", "available": {"volume_uL": 2.0}}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", str(source), "--inventory-check", str(inventory), "--json"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    result = payload["report"]["external_inventory"]
    assert result["checked"] is True
    assert result["sufficient"] is False
    assert result["items"] == [
        {
            "name": "Stock",
            "sufficient": False,
            "required": {"volume_uL": 5.0, "mass_mg": None, "count_cells": None},
            "available": {"volume_uL": 2.0, "mass_mg": None, "count_cells": None},
            "shortage": {"volume_uL": 3.0, "mass_mg": None, "count_cells": None},
            "remaining": {"volume_uL": 0.0, "mass_mg": None, "count_cells": None},
        }
    ]


def test_cli_does_not_treat_trailing_name_as_protocol_entry(tmp_path, monkeypatch):
    source = tmp_path / "script_entry.culs"
    source.write_text('let sample = tube(label = "S", capacity = 100uL);\nreturn sample;\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "Wrapper", "--json"])

    with pytest.raises(FileNotFoundError, match="Wrapper"):
        main()


def test_execute_pipeline_rejects_multiple_entry_sources(tmp_path):
    first = tmp_path / "first.culs"
    second = tmp_path / "second.culs"
    first.write_text('return "first";\n', encoding="utf-8")
    second.write_text('return "second";\n', encoding="utf-8")

    with pytest.raises(ValueError, match="RUN_SINGLE_ENTRY_SOURCE_REQUIRED"):
        execute_pipeline([first, second])


def test_execute_pipeline_rejects_entry_source_without_executable_entry(tmp_path):
    source = tmp_path / "definitions.culs"
    source.write_text("protocol First {}\nprotocol Second {}\n", encoding="utf-8")

    bundle = execute_pipeline([source])

    assert not bundle["output"]["ok"]
    assert bundle["returns"] == {}
    assert bundle["run"]["events"] == []
    assert bundle["run"]["state"]["step_status"] == {}
    assert [diagnostic["code"] for diagnostic in bundle["run"]["diagnostics"]] == [
        "ENTRY_NO_ENTRYPOINT"
    ]
    assert bundle["run"]["diagnostics"][0]["severity"] == "error"


def test_cli_entry_source_without_executable_entry_exits_nonzero(tmp_path, monkeypatch, capsys):
    source = tmp_path / "definitions.culs"
    source.write_text("protocol First {}\nprotocol Second {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--json"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert not payload["ok"]
    assert payload["returns"] == {}
    assert payload["report"]["execution"]["diagnostic_count"] == 1
    assert payload["report"]["alerts"] == [
        "ENTRY_NO_ENTRYPOINT: No executable entrypoint; add top-level script statements"
    ]


def test_cli_multi_input_runs_as_independent_batch(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.culs"
    second = tmp_path / "second.culs"
    first.write_text('let sample = tube(label = "FIRST", capacity = 100uL);\nreturn sample;\n', encoding="utf-8")
    second.write_text('let sample = tube(label = "SECOND", capacity = 100uL);\nreturn sample;\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(first), str(second), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "culsma_batch_run_output_v1"
    assert payload["ok"]
    assert [Path(item["input"]).name for item in payload["runs"]] == ["first.culs", "second.culs"]
    assert [item["output"]["returns"]["entry"]["value"]["id"] for item in payload["runs"]] == [
        "container/entry/entry.s0%3A%3Aalloc/sample",
        "container/entry/entry.s0%3A%3Aalloc/sample",
    ]
    assert [item["output"]["returns"]["entry"]["value"]["label"] for item in payload["runs"]] == [
        "FIRST",
        "SECOND",
    ]
    assert [
        item["output"]["report"]["resource_summary"]["containers"]["touched_names"] for item in payload["runs"]
    ] == [["FIRST"], ["SECOND"]]
    assert captured.err == ""


def test_cli_multi_input_prints_batch_human_summary(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.culs"
    second = tmp_path / "second.culs"
    first.write_text('return "first";\n', encoding="utf-8")
    second.write_text('return "second";\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(first), str(second)])

    main()

    captured = capsys.readouterr()
    assert captured.out == (
        "Culsma batch ok\n"
        "\n"
        "runs:\n"
        "  first.culs: entry ok\n"
        "  second.culs: entry ok\n"
        "\n"
        "execution: 2/2 runs ok\n"
    )
    assert captured.err == ""


def test_cli_multi_input_writes_batch_artifacts(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.culs"
    second = tmp_path / "second.culs"
    artifacts_dir = tmp_path / "artifacts"
    first.write_text('return "first";\n', encoding="utf-8")
    second.write_text('return "second";\n', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", str(first), str(second), "--json", "--artifacts-dir", str(artifacts_dir)],
    )

    main()

    captured = capsys.readouterr()
    assert json.loads(captured.out)["schema"] == "culsma_batch_run_output_v1"
    assert sorted(path.name for path in artifacts_dir.iterdir()) == [
        "001_first",
        "002_second",
        "output.json",
        "summary.json",
    ]
    assert (artifacts_dir / "001_first" / "run.json").exists()
    assert (artifacts_dir / "002_second" / "run.json").exists()
    assert captured.err == ""


def test_execute_batch_pipeline_keeps_single_input_output_shape(tmp_path):
    source = tmp_path / "single.culs"
    source.write_text('return "single";\n', encoding="utf-8")

    output = execute_batch_pipeline([source])["output"]

    assert output["schema"] == "culsma_run_output_v1"


def test_run_entry_file_script_imported_file_script_is_definitions_only(tmp_path):
    library = tmp_path / "Bio.culs"
    library.write_text(
        """
protocol LibPrepare(sample) {
  return sample;
}
protocol LibQc(sample) {
  return sample;
}
let lib_demo = tube(label = "LIB_DEMO", capacity = 100uL);
Bio.LibPrepare(sample = lib_demo);
return lib_demo;
""",
        encoding="utf-8",
    )
    source = tmp_path / "run.culs"
    source.write_text(
        """
import Bio;
protocol LocalPrepare(sample) {
  return sample;
}
protocol LocalQc(sample) {
  return sample;
}
let sample = tube(label = "RUN_SAMPLE", capacity = 100uL);
Bio.LibPrepare(sample = sample);
LocalPrepare(sample = sample);
return sample;
""",
        encoding="utf-8",
    )

    output = execute_pipeline([source], library_roots=[tmp_path])["output"]
    returned_values = [entry["value"]["id"] for entry in output["returns"].values()]
    touched_names = output["report"]["resource_summary"]["containers"]["touched_names"]

    assert output["ok"]
    assert list(output["returns"]) == ["entry"]
    assert output["returns"]["entry"]["entry_kind"] == "script"
    assert returned_values == ["container/entry/entry.s0%3A%3Aalloc/sample"]
    assert touched_names == ["RUN_SAMPLE"]
    assert "LIB_DEMO" not in json.dumps(output)
    assert "__script__" not in json.dumps(output)


def test_cli_accepts_top_level_input_path_shorthand(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("CliSmoke ok")
    assert "AcquisitionSample (tube)" in captured.out
    assert captured.err == ""


def test_cli_human_summary_includes_returned_container_state(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out == (
        "CliSmoke ok\n"
        "\n"
        "return:\n"
        "  AcquisitionSample (tube)\n"
        "    volume: 1000 uL\n"
        "    mass: 1000 mg\n"
        "\n"
        "execution: 3/3 steps completed, 1 diagnostics\n"
        "alerts:\n"
        "  ENTRY_LEGACY_IMPLICIT_PROTOCOL: Implicitly running protocol 'CliSmoke' is deprecated; add top-level script statements\n"
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


def test_cli_machine_output_projects_named_container_group_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "group_return.culs"
    source.write_text(
        """
protocol GroupReturn returns (wells) {
  let a1 = well(label = "A1", capacity = 50uL);
  let a2 = well(label = "A2", capacity = 50uL);
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  a1 << [mix:20uL];
  a2 << [mix:20uL];
  let wells_group = group([a1, a2]);
  return wells = wells_group;
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    group = payload["returns"]["GroupReturn"]["bindings"]["wells"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["label"] for member in group["members"]] == ["A1", "A2"]
    assert all(member["id"].startswith("container/group_return.GroupReturn/") for member in group["members"])
    assert [member["container_kind"] for member in group["members"]] == ["well", "well"]
    assert [member["volume_uL"] for member in group["members"]] == [20, 20]
    assert payload["report"]["schema"] == "lab_report_v1"
    assert captured.err == ""


def test_cli_machine_output_projects_plate_selector_group_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "plate_selector_return.culs"
    source.write_text(
        """
protocol SelectorReturn returns (wells) {
  let plate96 = plate(label = "QPCR96", format = "96well", carrier_id = "PlateA");
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  plate96[A1:A2] << [mix:10uL];
  return wells = plate96[A1:A2];
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source), "--json"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    group = payload["returns"]["SelectorReturn"]["bindings"]["wells"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["label"] for member in group["members"]] == ["QPCR96_A1", "QPCR96_A2"]
    assert all(member["id"].startswith("container/plate_selector_return.SelectorReturn/") for member in group["members"])
    assert [member["container_kind"] for member in group["members"]] == ["well", "well"]
    assert [member["volume_uL"] for member in group["members"]] == [10, 10]
    assert captured.err == ""


def test_cli_human_summary_summarizes_container_group_return(tmp_path, monkeypatch, capsys):
    source = tmp_path / "group_return.culs"
    source.write_text(
        """
protocol GroupReturn returns (wells) {
  let a1 = well(label = "A1", capacity = 50uL);
  let a2 = well(label = "A2", capacity = 50uL);
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  a1 << [mix:20uL];
  a2 << [mix:20uL];
  let wells_group = group([a1, a2]);
  return wells = wells_group;
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["culsma", "run", str(source)])

    main()

    captured = capsys.readouterr()
    assert captured.out.startswith("GroupReturn ok")
    assert "return:" in captured.out
    assert "wells:\n    container group: 2 wells" in captured.out
    assert "A1 (well)" in captured.out
    assert "volume: 20 uL" in captured.out
    assert "A2 (well)" in captured.out
    assert "None" not in captured.out
    assert captured.err == ""


def test_cli_run_writes_primary_result_when_output_is_requested(tmp_path, monkeypatch, capsys):
    source = _write_smoke_source(tmp_path)
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--input", str(source), "--json"])

    main()

    stdout_payload = json.loads(capsys.readouterr().out)
    output_path = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(source), "--output", str(output_path)],
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
    source = _write_smoke_source(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(source), "--json", "--artifacts-dir", str(artifacts_dir)],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "culsma_run_output_v1"
    assert payload["report"]["schema"] == "lab_report_v1"
    assert payload["returns"]["CliSmoke"]["value"]["id"] == (
        "container/cli_smoke.CliSmoke/p0.s0%3A%3Aalloc/sample"
    )
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
    source = _write_smoke_source(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        sys,
        "argv",
        ["culsma", "run", "--input", str(source), "--artifacts-dir", str(artifacts_dir)],
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
