"""Execute the actual Section 3 listings with their displayed inputs and calls.

These are checks of the paper's illustrations, separate from benchmark metrics.
New program definitions live in the TeX manuscript, not in benchmark copies.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMIT = "5364676bc2437b4981a00ce0133c730af243e469"


def listing(text, label):
    for match in re.finditer(r"\\begin\{lstlisting\}\[(.*?)\]\s*\n(.*?)\\end\{lstlisting\}", text, re.S):
        if "label={" + label + "}" in match[1]:
            return match[2]
    raise ValueError(f"Missing displayed listing: {label}")


def programs(text):
    yield "pcr", listing(text, "lst:pcr-comparison")
    yield "flow", listing(text, "lst:flow-comparison")
    yield "magnetic", listing(text, "lst:magnetic-capture")
    yield "fractions", listing(text, "lst:fraction-analysis")


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (actual, expected)


def indexed(material, name):
    matches = [value for key, value in material["indexed_bindings"].items()
               if key == name or key.endswith("_" + name)]
    assert len(matches) == 1, (name, material["indexed_bindings"])
    return matches[0]


def check_pcr_flow(name, artifacts):
    containers = artifacts["material_state"]["containers"]
    if name == "pcr":
        products = [c for c in containers.values()
                    if c["metadata"].get("label") == "PCR reaction"]
        assert len(products) == 1
        assert products[0]["volume_uL"] == 50
        assert products[0]["components"] == {
            "TEMPLATE": 1, "FORWARD": 2.5, "REVERSE": 2.5,
            "MASTER_MIX": 25, "WATER": 19}
        sources = [c for c in containers.values() if c is not products[0]]
        assert len(sources) == 5
        assert all(math.isclose(c["volume_uL"], 0, abs_tol=1e-9) for c in sources)
        return {"reaction_volume_uL": 50,
                "declared_inputs_fully_transferred": True,
                "components_uL": dict(products[0]["components"]),
                "declared_components_retained": True}

    observations = list(artifacts["data_objects"].values())
    assert len(observations) == 1
    observation = observations[0]
    subject = observation["subject_ref"]
    assert subject["unit_kind"] == "single_cell"
    assert containers[subject["source_ref"]]["metadata"]["label"] == "Cells for staining"
    assert subject["panel_ref"]["items"] == [
        "CD45", "CD3", "CD4", "CD8", "CD19", "LiveDead"]
    retained = containers[subject["source_ref"]]
    waste = next(c for c in containers.values()
                 if c["metadata"].get("label") == "Wash waste")
    assert retained["component_quantities"]["PBMC"] == {
        "dimension": "count", "unit": "cells", "value": 1000000}
    assert waste["component_quantities"]["PBMC"]["value"] == 0
    assert retained["components"]["FSB"] == 500
    assert waste["components"]["FSB"] == 2070
    expected_stains = {"ANTI_CD45": 5, "ANTI_CD3": 5,
                       "ANTI_CD4": 5, "ANTI_CD8": 5,
                       "ANTI_CD19": 5, "VIABILITY_DYE": 5}
    for content, amount in expected_stains.items():
        assert math.isclose(retained["components"][content], amount, abs_tol=1e-9)
        assert math.isclose(waste["components"].get(content, 0), 5 - amount, abs_tol=1e-9)
    expected_totals = {"FSB": 2570,
                       **{key: 5 for key in expected_stains}}
    for content, total in expected_totals.items():
        actual = sum(c["components"].get(content, 0) for c in containers.values())
        assert math.isclose(actual, total, abs_tol=1e-9)
    assert math.isclose(sum(
        c.get("component_quantities", {}).get("PBMC", {}).get("value", 0)
        for c in containers.values()), 1000000, abs_tol=1e-9)
    remaining = {}
    for content, total in expected_totals.items():
        value = round(total - retained["components"].get(content, 0)
                      - waste["components"].get(content, 0), 9)
        assert value >= -1e-9
        remaining[content] = 0.0 if math.isclose(value, 0, abs_tol=1e-9) else value
    fields = observation["result"]
    assert fields["sample_id"] == "sample_A"
    assert fields["control_role"] == "fully_stained"
    unset = {"signal", "channel", "event_id", "fsc_a", "fsc_h", "ssc_a",
             "cd45_raw_signal", "cd3_raw_signal", "cd4_raw_signal",
             "cd8_raw_signal", "cd19_raw_signal", "viability_raw_signal",
             "acquisition_config_id", "acquisition_qc_pass"}
    assert set(fields) == unset | {"sample_id", "control_role"}
    assert all(fields[key] is None for key in unset)
    return {"single_cell_subject_bound_to_processed_sample": True,
            "six_marker_panel_retained": True,
            "initial_cell_count": 1000000,
            "initial_cell_suspension_volume_uL": 70,
            "declared_component_totals_conserved": True,
            "material_state_uL": {
                "retained_sample": {
                    content: round(retained["components"].get(content, 0), 9)
                    for content in expected_totals
                },
                "waste": {
                    content: round(waste["components"].get(content, 0), 9)
                    for content in expected_totals
                },
                "remaining_stock": remaining,
            },
            "sample_and_control_fields_populated": True,
            "measurement_fields_unset": True}


def check_magnetic(artifacts):
    material = artifacts["material_state"]
    ids = indexed(material, "magnetic_result")
    outputs = [material["containers"][ids[str(i)]] for i in range(2)]
    target_amounts = []
    target = None
    for output in outputs:
        entries = output["component_entries"]
        amount = sum(e["quantity"]["value"] * 1000 for e in entries
                     if e["content_ref"] == "TARGET_PROTEIN")
        target_amounts.append(amount)
        for entry in entries:
            if entry["content_ref"] == "TARGET_PROTEIN" and entry["amount"] > 0:
                target = entry
                associated = [e for e in entries if e["entry_id"] == entry.get("associated_with")]
    expected = [1, 0]
    for actual, wanted in zip(target_amounts, expected):
        close(actual, wanted)
    close(sum(target_amounts), 1)
    close(outputs[0]["component_quantities"]["MAGNETIC_BEADS"]["value"], 10)
    assert target["relation"] == "bead_bound"
    assert target["relationship_source"] == "author_transition"
    assert len(associated) == 1 and associated[0]["content_ref"] == "MAGNETIC_BEADS"
    return {"target_outputs_ug": target_amounts, "target_relation": target["relation"],
            "association": "MAGNETIC_BEADS",
            "beads_retained_mg": 10, "target_residual_ug": abs(sum(target_amounts) - 1)}


def check_fractions(artifacts, events):
    material = artifacts["material_state"]
    containers = material["containers"]
    slot_groups = [value for key, value in material["indexed_bindings"].items()
                   if key.endswith("_fractions")]
    assert len(slot_groups) == 2
    assert all(set(slots) == {"0", "1", "2"} for slots in slot_groups)
    completed = [e.payload for e in events if e.kind == "STEP_COMPLETED"]
    mutations = [p["material_delta"] for p in completed
                 if p.get("material_delta", {}).get("op") == "Mutation"]
    groups = {group["binding"]: group for group in artifacts["data_groups"].values()}
    assert set(groups) == {"result_A", "result_B"}
    for suffix in ("A", "B"):
        code = f"SAMPLE_{suffix}"
        slots = next(slots for slots in slot_groups
                     if code in containers[slots["0"]]["components"])
        group = groups[f"result_{suffix}"]
        well_ids = group["resolved_samples"]
        assert len(well_ids) == 6
        wells = {containers[well_id]["metadata"]["label"].split("_")[-1]:
                 (well_id, containers[well_id]) for well_id in well_ids}
        assert set(wells) == {"A1", "A2", "A3", "B1", "B2", "B3"}
        for i in range(3):
            source_id = slots[str(i)]
            dest_id, dest = wells[f"A{i + 1}"]
            close(containers[source_id]["volume_uL"], 90)
            close(dest["components"][code], 10)
            close(dest["components"]["DILUENT"], 40)
            transfers = [s for m in mutations if m["target"] == dest_id
                         for s in m["sources"] if s["source"] == source_id]
            assert len(transfers) == 1
            close(transfers[0]["qty"]["value"], 10)
        for i, dose in enumerate([5, 10, 20], 1):
            well = wells[f"B{i}"][1]
            close(well["components"]["STANDARD"], dose)
            close(well["components"]["DILUENT"], 50 - dose)
        for _, well in wells.values():
            close(well["volume_uL"], 150)
            close(well["components"]["REAGENT"], 100)
    for content, total in {"SAMPLE_A": 300, "SAMPLE_B": 300, "STANDARD": 70,
                           "DILUENT": 470, "REAGENT": 1200}.items():
        close(sum(c["components"].get(content, 0) for c in containers.values()), total)
    observations = list(artifacts["data_objects"].values())
    assert len(observations) == 12
    assert all(o["family"] == "img" for o in observations)
    assert {o["resolved_sample"] for o in observations} == {
        well_id for group in groups.values() for well_id in group["resolved_samples"]}
    assert all(v is None for o in observations for v in o["result"].values())
    constrained = [p for p in completed
                   if "high_precision" in p.get("gate", {}).get("constraint", {}).get("requirements", [])]
    assert len(constrained) == 12
    return {"ordered_fraction_to_well_paths": ["0 -> A1", "1 -> A2", "2 -> A3"],
            "standard_doses_uL": [5, 10, 20], "assay_well_volumes_uL": [150] * 6,
            "protocol_calls": 2, "observation_groups": 2,
            "well_observations": 12, "constrained_additions": 12,
            "all_measurement_fields_unset": True, "component_totals_conserved": True}


def write_pcr_execution_result(console_text, output_dir):
    listing = [
        "% Generated by scripts/check_manuscript_examples.py; do not edit.",
        r"\begin{lstlisting}[language={},basicstyle=\footnotesize\ttfamily,caption={Compact execution result generated for the PCR example.},label={lst:pcr-execution-result}]",
        console_text.rstrip(),
        r"\end{lstlisting}",
    ]
    (output_dir / "pcr_execution_result.tex").write_text("\n".join(listing) + "\n")


def write_flow_execution_result(console_text, output_dir):
    listing = [
        "% Generated by scripts/check_manuscript_examples.py; do not edit.",
        r"\begin{lstlisting}[language={},basicstyle=\footnotesize\ttfamily,caption={Compact execution result generated for the flow-cytometry example.},label={lst:flow-execution-result}]",
        console_text.rstrip(),
        r"\end{lstlisting}",
    ]
    (output_dir / "flow_execution_result.tex").write_text("\n".join(listing) + "\n")


def write_magnetic_execution_result(console_text, output_dir):
    listing = [
        "% Generated by scripts/check_manuscript_examples.py; do not edit.",
        r"\begin{lstlisting}[language={},basicstyle=\footnotesize\ttfamily,caption={Compact execution result generated for the magnetic-bead capture example.},label={lst:magnetic-execution-result}]",
        console_text.rstrip(),
        r"\end{lstlisting}",
    ]
    (output_dir / "magnetic_execution_result.tex").write_text("\n".join(listing) + "\n")


def write_fraction_execution_result(console_text, output_dir):
    listing = [
        "% Generated by scripts/check_manuscript_examples.py; do not edit.",
        r"\begin{lstlisting}[language={},basicstyle=\footnotesize\ttfamily,float=tp,caption={Compact execution result generated for the plate-based fraction-analysis example.},label={lst:fraction-execution-result}]",
        console_text.rstrip(),
        r"\end{lstlisting}",
    ]
    (output_dir / "fraction_execution_result.tex").write_text("\n".join(listing) + "\n")


def run_compact_exports(culsma_cli, sources, output_dir):
    if not culsma_cli.exists():
        raise FileNotFoundError(f"Culsma CLI not found: {culsma_cli}")
    results = {}
    for name, source_path in sources.items():
        result_path = output_dir / f"{name}.results.json"
        subprocess.run(
            [str(culsma_cli), str(source_path), "--results", str(result_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(result_path.read_text())
        if set(result) != {"materials", "resources", "returns"}:
            raise RuntimeError(name, "unexpected compact-result fields", sorted(result))
        results[name] = result
    python = culsma_cli.parent / "python"
    version = subprocess.check_output([
        str(python), "-c",
        "from importlib.metadata import version; print(version('culsma'))",
    ], text=True).strip()
    return results, version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--culsma-repo", type=Path, default=ROOT.parents[1] / "Culsma")
    parser.add_argument("--output", type=Path, default=ROOT / "output/manuscript_examples")
    parser.add_argument("--tex-output-dir", type=Path, default=ROOT / "sections/generated")
    parser.add_argument("--culsma-cli", type=Path)
    parser.add_argument("--program-dir", type=Path, default=ROOT / "modules", help="Directory containing example-01 through example-04")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.tex_output_dir.mkdir(parents=True, exist_ok=True)
    if args.program_dir:
        inputs = [(name, (args.program_dir / f"example-{index:02d}" / "protocol.culs").read_text())
                  for index, name in enumerate(("pcr", "flow", "magnetic", "fractions"), 1)]
        source_identity = {"input_mode": "exported_programs"}
    else:
        text = (ROOT / "sections/08_modeling_principles_validation.tex").read_text()
        inputs = list(programs(text))
        source_identity = {"manuscript_sha256": hashlib.sha256(text.encode()).hexdigest()}
    archive = subprocess.check_output(["git", "-C", str(args.culsma_repo), "archive", COMMIT, "src", "pyproject.toml"])
    summary = {"implementation_commit": COMMIT, "python": platform.python_version(),
               "execution_backend": "deterministic_reference", "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "source_archive_sha256": hashlib.sha256(archive).hexdigest(),
               **source_identity, "examples": {}}
    source_paths = {}
    with tempfile.TemporaryDirectory(prefix="culsma-manuscript-") as temp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(temp, filter="data")
        sys.path.insert(0, str(Path(temp) / "src"))
        import lark
        from culsma.parser.parser import parse
        from culsma.frontend.resolver import resolve_program
        from culsma.pipeline.compile import compile_ast
        from culsma.pipeline.validate import validate
        from culsma.pipeline.typecheck import typecheck
        from culsma.pipeline.plan import lower_ir_to_plan
        from culsma.runtime.executor import run
        from culsma.driver.stub import StubDriver
        summary["lark"] = lark.__version__
        for name, source in inputs:
            source_path = args.output / f"{name}.culs"
            source_path.write_text(source)
            source_paths[name] = source_path
            compiled = compile_ast(resolve_program(parse(source)).prepared_program)
            valid = validate(compiled.ir, analysis=compiled.analysis)
            if not valid.ok:
                raise RuntimeError(name, [d.to_dict() for d in valid.diagnostics])
            typed = typecheck(valid.ir, analysis=compiled.analysis)
            if not typed.ok:
                raise RuntimeError(name, [d.to_dict() for d in typed.diagnostics])
            plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
            if plan.diagnostics:
                raise RuntimeError(name, [d.to_dict() for d in plan.diagnostics])
            result = run(plan=plan, driver=StubDriver())
            state = result.state.to_dict()
            (args.output / f"{name}.json").write_text(json.dumps(state, indent=2) + "\n")
            (args.output / f"{name}.events.json").write_text(json.dumps(
                [e.to_dict() for e in result.events], indent=2) + "\n")
            if result.user_result is None:
                raise RuntimeError(name, "missing user-facing run report")
            (args.output / f"{name}.report.json").write_text(
                json.dumps(result.user_result, indent=2) + "\n")
            if not result.ok:
                raise RuntimeError(name, [d.to_dict() for d in result.diagnostics])
            artifacts = state["artifacts"]
            if name in ("pcr", "flow"):
                checks = check_pcr_flow(name, artifacts)
            elif name == "magnetic":
                checks = check_magnetic(artifacts)
            elif name == "fractions":
                checks = check_fractions(artifacts, result.events)
            summary["examples"][name] = {"ok": True, "checks": checks,
                "input_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "completed_steps": sum(s == "completed" for s in state["step_status"].values())}
            print(name + ": passed", flush=True)
    culsma_cli = args.culsma_cli or args.culsma_repo / ".venv/bin/culsma"
    compact_results, compact_version = run_compact_exports(culsma_cli, source_paths, args.output)
    summary["compact_results"] = {
        "culsma_version": compact_version,
        "fields": ["materials", "resources", "returns"],
        "files": {
            name: {
                "path": f"{name}.results.json",
                "sha256": hashlib.sha256((args.output / f"{name}.results.json").read_bytes()).hexdigest(),
            }
            for name in compact_results
        },
    }
    pcr_console = subprocess.check_output(
        [str(culsma_cli), str(source_paths["pcr"])], text=True
    )
    write_pcr_execution_result(pcr_console, args.tex_output_dir)
    flow_console = subprocess.check_output(
        [str(culsma_cli), str(source_paths["flow"])], text=True
    )
    write_flow_execution_result(flow_console, args.tex_output_dir)
    magnetic_console = subprocess.check_output(
        [str(culsma_cli), str(source_paths["magnetic"])], text=True
    )
    write_magnetic_execution_result(magnetic_console, args.tex_output_dir)
    fraction_console = subprocess.check_output(
        [str(culsma_cli), str(source_paths["fractions"])], text=True
    )
    write_fraction_execution_result(fraction_console, args.tex_output_dir)
    import shutil
    for index, name in enumerate(("pcr", "flow", "magnetic", "fractions"), 1):
        target = args.output / "modules" / f"example-{index:02d}" / "results"
        target.mkdir(parents=True, exist_ok=True)
        for path in args.output.glob(name + ".*"):
            shutil.move(str(path), target / path.name)
        summary["compact_results"]["files"][name]["path"] = str(
            (target / f"{name}.results.json").relative_to(args.output))
    (args.output / "examples-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
