from __future__ import annotations

from pathlib import Path

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse, parse_file
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


ROOT = Path(__file__).resolve().parents[1]
CURRENT_FIXTURES = [
    ROOT / "tests" / "fixtures_parser" / "current_frontend_core.culs",
    ROOT / "tests" / "fixtures_parser" / "current_frontend_readout.culs",
]


def _compile_source(source: str):
    frontend = resolve_program(parse(source))
    return compile_ast(frontend.prepared_program)


def _plan_from_source(source: str):
    compiled = _compile_source(source)
    sem = validate(compiled.ir, analysis=compiled.analysis)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]
    return lower_ir_to_plan(typ.ir), sem.diagnostics + typ.diagnostics


def test_current_frontend_fixtures_use_canonical_content_taxonomy():
    legacy_tokens = (
        'kind = "biosample"',
        "kind = biosample",
        'kind = "reagent"',
        "kind = reagent",
        'kind = "buffer"',
        "kind = buffer",
        "blood(",
        "reagent(",
        "buffer(",
    )
    for fixture in CURRENT_FIXTURES:
        source = fixture.read_text(encoding="utf-8")
        assert not any(token in source for token in legacy_tokens), fixture


def test_current_frontend_fixtures_compile_without_taxonomy_compat_warnings():
    for fixture in CURRENT_FIXTURES:
        frontend = resolve_program(parse_file(fixture))
        compiled = compile_ast(frontend.prepared_program)
        result = validate(compiled.ir, analysis=build_compile_analysis(compiled.ir))
        codes = {d.code for d in result.diagnostics}

        assert result.ok, [d.to_dict() for d in result.diagnostics]
        assert "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED" not in codes


def test_reference_style_content_attrs_source_runs_end_to_end():
    plan, diagnostics = _plan_from_source(
        """
protocol T {
  let source = tube(
    label = "Source",
    capacity = 100uL,
    load = [content(kind = formulation, type = buffer, code = "PBS1", attrs = { role: wash, state: ready }):10uL]
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())
    registry = result.state.artifacts["material_state"]["content_registry"]

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert not diagnostics
    assert registry["PBS1"]["content_kind"] == "formulation"
    assert registry["PBS1"]["content_type"] == "buffer"
    assert registry["PBS1"]["content_attrs"] == {"role": "wash", "state": "ready"}


def test_frontend_file_entry_param_drives_static_schedule_endpoint(tmp_path: Path):
    source = tmp_path / "cdna.culs"
    source.write_text(
        """
protocol PcrSelectedCycles(selected_amplification_cycles = 7) {
  let cdna = tube(
    label = "CDNA",
    capacity = 200uL,
    load = [content(kind = bio_molecule_or_virus, type = dna, code = "CDNA"):100uL]
  );

  repeat selected_cycle in schedule(start = 1, end = selected_amplification_cycles, step = 1) {
    with env(thermal = 98C, duration = 20s) {
      hold(cdna);
    }
  }

  return cdna;
}
""",
        encoding="utf-8",
    )

    frontend = resolve_files([source], include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]

    plan = lower_ir_to_plan(
        typ.ir,
        entry_args_by_protocol={"PcrSelectedCycles": {"selected_amplification_cycles": 4}},
    )

    assert not plan.diagnostics
    assert [step.op for step in plan.plans[0].steps].count("env_hold") == 4


def test_legacy_content_sugar_is_compatibility_surface_not_current_frontend():
    compiled = _compile_source(
        """
protocol T {
  let source = tube(label = "Source", load = [buffer(code = "BUF1", type = "wash_buffer"):10uL]);
}
"""
    )

    result = validate(compiled.ir, analysis=compiled.analysis)
    warnings = [d for d in result.diagnostics if d.code == "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED"]

    assert result.ok
    assert len(warnings) == 1
    assert 'content(kind="formulation", type="buffer", attrs={role: "wash"})' in warnings[0].message
