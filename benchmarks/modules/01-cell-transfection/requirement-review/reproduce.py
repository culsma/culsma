"""Check the submitted and revised Module 01 transfers with Culsma 1.0.7."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import culsma
import lark
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run

HERE = Path(__file__).resolve().parent
BENCHMARKS = HERE.parents[2]
sys.path.insert(0, str(BENCHMARKS))
from reproduce import assess  # shared source-step correspondence rule

RUNTIME = "5364676bc2437b4981a00ce0133c730af243e469"
SOURCE_WELLS = {"NonTargetingDeliveryMixture": "A2", "DeletionDeliveryMixture": "A3"}


def main():
    assert culsma.__version__ == "1.0.7" and lark.__version__ == "1.3.1"
    runtime = Path(culsma.__file__).resolve().parents[1]
    archive = subprocess.check_output(["git", "-C", str(BENCHMARKS.parent), "archive", RUNTIME, "src"])
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle.getmembers():
            if member.isfile():
                local = runtime / Path(member.name).relative_to("src")
                assert local.read_bytes() == bundle.extractfile(member).read(), local

    frozen = json.loads((BENCHMARKS / "manifest.json").read_text())["input_sha256"]
    report = {"runtime_commit": RUNTIME, "culsma": culsma.__version__, "lark": lark.__version__,
              "driver": "StubDriver", "cases": {}}
    for name, folder, supported in [("submitted", HERE / "submitted", set()), ("revised", HERE, {"dropwise"}),
                                    ("revised_unsupported", HERE, set())]:
        coverage = assess(folder, RUNTIME, culsma.__version__)
        original = HERE.parent.relative_to(BENCHMARKS)
        assert coverage["source_sha256"] == frozen[str(original / "source.md")]
        if name == "submitted":
            submitted = subprocess.check_output(["git", "-C", str(BENCHMARKS.parent),
                "show", "687364f:benchmarks/modules/01-cell-transfection/protocol.culs"])
            assert (folder / "protocol.culs").read_bytes() == submitted
        else:
            assert (folder / "protocol.culs").read_bytes() == (HERE.parent / "protocol.culs").read_bytes()
        expected_gaps = [10, 11] if name == "submitted" else []
        assert coverage["total_steps"] == 13
        assert coverage["matched_steps"] == 13 - len(expected_gaps)
        assert coverage["issues"] == [{"step": n, "reason": "coverage_gap"} for n in expected_gaps]
        program = (folder / "protocol.culs").read_text()
        compiled = compile_ast(resolve_program(parse(program)).prepared_program)
        valid = validate(compiled.ir, analysis=compiled.analysis)
        assert valid.ok, valid.diagnostics
        typed = typecheck(valid.ir, analysis=compiled.analysis)
        assert typed.ok, typed.diagnostics
        plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
        assert not plan.diagnostics, plan.diagnostics
        result = run(plan=plan, driver=StubDriver(supported_requirements=supported))
        containers = result.state.artifacts["material_state"]["containers"]
        volumes = {c["metadata"]["label"]: c["volume_uL"] for c in containers.values()}
        transfers = []
        for event in result.events:
            if event.kind != "STEP_COMPLETED":
                continue
            requirements = event.payload.get("gate", {}).get("constraint", {}).get("requirements", [])
            for move in event.payload.get("material_delta", {}).get("sources", []):
                source = containers[move["source"]]["metadata"]["label"]
                if source in SOURCE_WELLS:
                    target = containers[move["target"]]["metadata"]["label"]
                    assert target == "Module01EditingPlate_" + SOURCE_WELLS[source]
                    assert move["mode"] == "full" and move["moved_uL"] == 73.6
                    assert requirements == (["dropwise"] if name == "revised" else [])
                    transfers.append({"source": source, "target": target, "mode": move["mode"],
                                      "moved_uL": move["moved_uL"], "requirements": requirements,
                                      "program_line": event.span.line})
                else:
                    assert "dropwise" not in requirements
        diagnostics = [d.to_dict() for d in result.diagnostics]
        if name == "revised_unsupported":
            assert not result.ok and not transfers
            rejection, = [d for d in diagnostics if d["code"] == "RT_DRIVER_REQUIREMENT_UNSUPPORTED"]
            line = program.splitlines()[rejection["span"]["line"] - 1]
            assert "non_targeting_cells <<" in line and "dropwise" in line
            assert all(volumes[label] == 73.6 for label in SOURCE_WELLS)
            assert all(volumes["Module01EditingPlate_" + w] == 1000 for w in SOURCE_WELLS.values())
        else:
            assert result.ok and not diagnostics and result.user_result["execution"]["completed_steps"] == 63
            assert [t["source"] for t in transfers] == list(SOURCE_WELLS)
            assert all(volumes[label] == 0 for label in SOURCE_WELLS)
        report["cases"][name] = {"coverage": coverage, "supported": sorted(supported),
                                 "execution": result.user_result["execution"], "transfers": transfers,
                                 "source_remaining_uL": {k: volumes[k] for k in SOURCE_WELLS},
                                 "diagnostics": diagnostics}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
