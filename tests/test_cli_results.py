from __future__ import annotations

import json
import sys

import pytest

from culsma.cli import execute_pipeline, format_terminal_result, main


MATERIAL_SOURCE = """
let water = tube(label = "Water", capacity = 2mL, load = [
  content(kind = ContentKind.CHEMICAL, type = ContentType.SOLVENT, code = "H2O"):100uL
]);
let reaction = tube(label = "Reaction", capacity = 200uL);
let spare = tube(label = "Spare", capacity = 0.2mL);
reaction << [water:19uL];
return reaction;
"""

OBSERVATION_SOURCE = """
let sample = tube(label = "Cells", capacity = 2mL);
let panel = markers(["CD3", "CD19"]);
let events = stream(sample = sample, unit = single_cell, panel = panel);
let schema = data_schema(label = "Acquisition", fields = [sample_id, control_role, fsc_a]);
let observation = img(sample = events, quantity = customized, schema_ref = schema, save_raw = true);
observation.result.sample_id = "sample_A";
observation.result.control_role = "fully_stained";
return observation;
"""

FLOW_MATERIAL_SOURCE = """
let cells = tube(label = "Cells for staining", capacity = 5mL, load = [
  content(kind = bio_cellular, type = cell_population, code = "PBMC",
    attrs = { state: suspension }):70uL]);
let stain = tube(label = "Six-stain panel", capacity = 100uL, load = [
  content(kind = bio_molecule_or_virus, type = protein,
    code = "ANTI_CD45", attrs = { role: antibody }):30uL]);
let buffer = tube(label = "Wash buffer", capacity = 5mL, load = [
  content(kind = formulation, type = ContentType.BUFFER, code = "FSB"):3mL]);
let waste = tube(label = "Wash waste", capacity = 5mL);
cells << [stain:30uL];
cells << [buffer:2mL];
let separated = sep(sample = cells,
  program = centrifuge_program(drive = 300g, keep_source = "pellet"),
  component_fates = {
    PBMC: { supernatant: 0%, pellet: 100% },
    FSB: { supernatant: 100%, pellet: 0% },
    ANTI_CD45: { supernatant: 99.9%, pellet: 0.1% }
  });
waste << [separated[0]];
return cells;
"""


def test_results_file_has_three_fields_and_keeps_legacy_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / "reaction.culs"
    source.write_text(MATERIAL_SOURCE)
    target = tmp_path / "nested" / "results.json"
    artifacts = tmp_path / "artifacts"
    monkeypatch.setattr(sys, "argv", [
        "culsma", str(source), "--results", str(target), "--artifacts-dir", str(artifacts)
    ])
    main()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    results = json.loads(target.read_text())
    assert set(results) == {"materials", "resources", "returns"}
    assert results["materials"] == [{"name": "Water", "amount": 19, "unit": "uL"}]
    assert results["resources"] == [
        {"kind": "tube", "capacity_uL": 200, "count": 2},
        {"kind": "tube", "capacity_uL": 2000, "count": 1},
    ]
    legacy = json.loads((artifacts / "output.json").read_text())
    assert legacy["schema"] == "culsma_run_output_v1"
    assert legacy["report"]["schema"] == "lab_report_v1"
    assert results["returns"] == legacy["returns"]
    assert "specifications" not in legacy["report"]["resource_summary"]["containers"]
    assert results["returns"]["entry"]["value"]["volume_uL"] == 19

    for option in ("--json", "--output"):
        output_path = tmp_path / "legacy.json"
        args = ["culsma", str(source), option]
        if option == "--output":
            args.append(str(output_path))
        monkeypatch.setattr(sys, "argv", args)
        main()
        captured = capsys.readouterr()
        actual = json.loads(captured.out if option == "--json" else output_path.read_text())
        assert actual == legacy


def test_default_console_shows_the_three_results(tmp_path, monkeypatch, capsys):
    source = tmp_path / "reaction.culs"
    source.write_text(MATERIAL_SOURCE)
    monkeypatch.setattr(sys, "argv", ["culsma", str(source)])
    main()
    text = capsys.readouterr().out
    assert text.startswith("materials:\n")
    assert "entry ok" not in text
    assert "materials:\n  Water: 19 uL" in text
    assert "resources:\n  2 x tube (200 uL)\n  1 x tube (2 mL)" in text
    assert "return:\n  Reaction (tube)\n    volume: 19 uL" in text
    assert "mass:" not in text
    assert "execution:" not in text


def test_results_report_declared_sample_input_instead_of_routed_fraction(tmp_path):
    source = tmp_path / "flow_materials.culs"
    source.write_text(FLOW_MATERIAL_SOURCE)
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    assert bundle["output"]["report"]["materials"]["reagent_consumption"] == [
        {
            "name": "Wash buffer",
            "roles": ["source"],
            "consumed_uL": 2000.0,
            "consumed_mL": 2.0,
            "consumed_mg": None,
        },
        {
            "name": "Cells for staining",
            "roles": ["dest", "sample"],
            "consumed_uL": 67.666,
            "consumed_mL": 0.067666,
            "consumed_mg": None,
        },
        {
            "name": "Six-stain panel",
            "roles": ["source"],
            "consumed_uL": 30.0,
            "consumed_mL": 0.03,
            "consumed_mg": None,
        },
    ]
    assert bundle["results"]["materials"] == [
        {"name": "Wash buffer", "amount": 2000.0, "unit": "uL"},
        {"name": "Cells for staining", "amount": 70.0, "unit": "uL"},
        {"name": "Six-stain panel", "amount": 30.0, "unit": "uL"},
    ]


def test_results_select_quantity_per_lot_before_same_name_aggregation(tmp_path):
    source = tmp_path / "same_name_materials.culs"
    source.write_text(
        FLOW_MATERIAL_SOURCE.replace('label = "Cells for staining"', 'label = "Shared"')
        .replace('label = "Six-stain panel"', 'label = "Shared"')
        .replace('attrs = { role: antibody }):30uL', 'attrs = { role: antibody }):100uL')
    )
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    assert bundle["results"]["materials"] == [
        {"name": "Wash buffer", "amount": 2000.0, "unit": "uL"},
        {"name": "Shared", "amount": 100.0, "unit": "uL"},
    ]


def test_observation_results_keep_null_fields_but_console_is_compact(tmp_path, monkeypatch, capsys):
    source = tmp_path / "observation.culs"
    source.write_text(OBSERVATION_SOURCE)
    target = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["culsma", str(source), "--results", str(target)])
    main()
    assert capsys.readouterr().out == ""
    results = json.loads(target.read_text())
    observation = results["returns"]["entry"]["value"]
    assert observation["kind"] == "data_ref"
    assert observation["result"]["fsc_a"] is None
    assert observation["result"]["sample_id"] == "sample_A"
    assert observation["subject_ref"]["panel_ref"]["items"] == ["CD3", "CD19"]
    assert results["resources"] == [{"kind": "tube", "capacity_uL": 2000, "count": 1}]

    monkeypatch.setattr(sys, "argv", ["culsma", str(source)])
    main()
    text = capsys.readouterr().out
    assert "data: single-cell acquisition" in text
    assert "panel: CD3, CD19" in text
    assert "sample_id: sample_A" in text
    assert "control_role: fully_stained" in text
    assert "fsc_a" not in text
    assert "driver_payload" not in text
    assert "None" not in text


def test_data_group_console_preview_does_not_truncate_json(tmp_path):
    source = tmp_path / "group.culs"
    source.write_text(OBSERVATION_SOURCE.replace("return observation;", """
let observations = data_group_ref(kind = acquisition);
repeat i in schedule(start = 1, end = 5, step = 1) {
  observations.items.append(observation);
}
return observations;
"""))
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    text = format_terminal_result(bundle)
    assert "data group: 5 items" in text
    assert text.count("sample_id: sample_A") == 3
    assert "2 more items" in text
    assert len(bundle["results"]["returns"]["entry"]["value"]["items"]) == 5


def test_results_skip_unexecuted_containers_and_keep_default_and_no_capacity(tmp_path):
    source = tmp_path / "resources.culs"
    source.write_text("""
let default_tube = tube(label = "Default");
let slide = surface(label = "Slide");
let decision = data_ref(kind = decision);
decision.result.enabled = false;
if decision.result.enabled {
  let skipped = tube(label = "Skipped", capacity = 123uL);
}
return default_tube;
""")
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    resources = bundle["results"]["resources"]
    assert len(resources) == 2
    assert {"kind": "surface", "capacity_uL": None, "count": 1} in resources
    tube = next(row for row in resources if row["kind"] == "tube")
    assert tube["capacity_uL"] > 0
    assert tube["count"] == 1
    assert bundle["output"]["report"]["resource_summary"]["containers"]["allocated_count"] == 3


def test_results_ignore_sample_role_in_unexecuted_branch(tmp_path):
    source = tmp_path / "skipped_sample.culs"
    source.write_text("""
let sample = tube(label = "Conditional sample", capacity = 2mL, load = [
  content(kind = bio_cellular, type = cell_population, code = "CELLS"):70uL
]);
let decision = data_ref(kind = decision);
decision.result.enabled = false;
if decision.result.enabled {
  with env(thermal = 4C, duration = 1min) {
    hold(sample = sample);
  }
}
return "done";
""")
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    assert bundle["results"]["materials"] == []


def test_results_list_explicit_device_once_from_completed_steps(tmp_path):
    source = tmp_path / "device.culs"
    source.write_text("""
let sample_one = tube(label = "First sample");
let sample_two = tube(label = "Second sample");
let first = sep(sample = sample_one,
  program = magnetic_program(duration = 1min, device = "magnetic-rack-1"));
let second = sep(sample = sample_two,
  program = magnetic_program(duration = 1min, device = "magnetic-rack-1"));
return second;
""")
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    assert {"kind": "device", "name": "magnetic-rack-1", "count": 1} in bundle["results"]["resources"]


def test_results_count_plate_as_one_carrier_and_summarize_observations(tmp_path):
    source = tmp_path / "plate.culs"
    source.write_text("""
let reagent = tube(label = "Reagent", capacity = 100uL, load = [
  content(kind = formulation, type = buffer, code = "REAGENT"):50uL
]);
let assay = plate(label = "Assay", format = "96well");
assay[A1:A2] << [reagent:10uL];
let signals = img(sample = assay[A1:A2], quantity = fluorescence);
return signals;
""")
    bundle = execute_pipeline([source])
    assert bundle["output"]["ok"]
    assert bundle["results"]["resources"] == [
        {"kind": "plate", "capacity_uL": None, "count": 1},
        {"kind": "tube", "capacity_uL": 100.0, "count": 1},
    ]
    assert "data group: 2 observations" in format_terminal_result(bundle)


def test_results_do_not_label_inferred_products_as_returns(tmp_path):
    source = tmp_path / "no_return.culs"
    source.write_text(MATERIAL_SOURCE.replace("return reaction;", ""))
    bundle = execute_pipeline([source])
    assert bundle["output"]["report"]["materials"]["final_products"]
    assert "value" not in bundle["results"]["returns"]["entry"]
    text = format_terminal_result(bundle)
    assert "return:\n  (no explicit return value)" in text
    assert "final products:" not in text


def test_results_include_only_used_imported_containers(tmp_path):
    source = tmp_path / "imported.culs"
    source.write_text("return external;")
    initial = tmp_path / "initial.json"
    initial.write_text(json.dumps({"containers": {
        "external": {
            "volume_uL": 10, "mass_mg": 0, "components": {},
            "metadata": {"kind": "tube", "capacity_uL": "200", "allocation_step_id": "previous.s0"},
        },
        "unlabelled": {"volume_uL": 0, "mass_mg": 0, "components": {}, "metadata": None},
    }}))
    bundle = execute_pipeline([source], material_state_path=initial)
    assert bundle["output"]["ok"]
    assert bundle["results"]["resources"] == [
        {"kind": "tube", "capacity_uL": 200, "count": 1}
    ]


def test_failed_results_file_is_partial_and_failure_is_visible(tmp_path, monkeypatch, capsys):
    source = tmp_path / "failed.culs"
    source.write_text(MATERIAL_SOURCE)
    target = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", [
        "culsma", str(source), "--results", str(target), "--fail-op", "AllocContainer"
    ])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Run failed" in captured.err
    results = json.loads(target.read_text())
    assert results["resources"] == []
    assert results["materials"] == []


@pytest.mark.parametrize("extra", [["--json"], ["--output", "legacy.json"]])
def test_results_rejects_conflicting_output_modes(tmp_path, monkeypatch, capsys, extra):
    target = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["culsma", "run", "--results", str(target), *extra])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "--results cannot be combined" in capsys.readouterr().err
    assert not target.exists()


def test_batch_results_preserve_independent_runs_in_input_order(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.culs"
    second = tmp_path / "second.culs"
    first.write_text('return "first";')
    second.write_text('return "second";')
    target = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["culsma", str(first), str(second), "--results", str(target)])
    main()
    assert capsys.readouterr().out == ""
    results = json.loads(target.read_text())
    assert len(results) == 2
    assert all(set(item) == {"materials", "resources", "returns"} for item in results)
    assert [item["returns"]["entry"]["value"] for item in results] == ["first", "second"]
