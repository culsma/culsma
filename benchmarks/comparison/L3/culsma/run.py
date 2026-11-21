"""Pinned Culsma repetition and runtime observation-dependent routing.

Uses the released StubDriver measurement-result fixture, as in the pinned
test_kernel_runtime.py observation-if tests. No real measurements are claimed.
"""
import hashlib
import json
from pathlib import Path
from culsma.parser.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run

OUT = Path(__file__).resolve().parent
SETUP = '''let source = tube(label = "source", capacity = 1.5mL, load = [
    content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER"):100uL]);
let target = tube(label = "target", capacity = 1.5mL);
let alternative = tube(label = "alternative", capacity = 1.5mL);
'''
BRANCH = SETUP + '''let obs = img(sample = source, quantity = fluorescence);
if obs.result.signal >= 1000 {
    target << [source:10uL];
} else {
    alternative << [source:20uL];
}
'''


def compile_plan(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis)
    typ = typecheck(sem.ir, analysis=compiled.analysis)
    assert sem.ok and typ.ok, [d.to_dict() for d in [*sem.diagnostics, *typ.diagnostics]]
    return lower_ir_to_plan(typ.ir, analysis=compiled.analysis)


def execute(plan, driver):
    result = run(plan=plan, driver=driver)
    containers = result.state.artifacts["material_state"]["containers"]
    return {"ok": result.ok, "diagnostics": [d.to_dict() for d in result.diagnostics],
            "volumes_ul": {v["metadata"]["label"]:v["volume_uL"] for v in containers.values()},
            "step_status": result.state.step_status,
            "skip_reasons": result.state.artifacts.get("skip_reasons", {}),
            "events": [e.to_dict() for e in result.events]}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"culsma_commit": "5364676bc2437b4981a00ce0133c730af243e469", "loops": {}, "branches": {}}
    for n in [2, 3]:
        source = SETUP + f'''repeat i in schedule(start = 1, end = {n}, step = 1) {{
    target << [source:10uL];
}}
'''
        (OUT / f"repeat_{n}.culs").write_text(source)
        report["loops"][str(n)] = execute(compile_plan(source), StubDriver())
    (OUT / "runtime_branch.culs").write_text(BRANCH)
    plan = compile_plan(BRANCH)
    report["branch_source_sha256"] = hashlib.sha256(BRANCH.encode()).hexdigest()
    report["same_plan_used_for_both_values"] = True
    for signal in [1250, 800]:
        report["branches"][str(signal)] = execute(plan, StubDriver(op_payloads={"img": {"result": {"signal": signal}}}))
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"loops": {k:v['volumes_ul'] for k,v in report['loops'].items()},
                      "branches": {k:v['volumes_ul'] for k,v in report['branches'].items()}}, indent=2))
