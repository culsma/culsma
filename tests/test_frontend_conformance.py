from __future__ import annotations

from pathlib import Path

import pytest

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


@pytest.mark.parametrize("quoted", [False, True], ids=["bare", "quoted"])
@pytest.mark.parametrize(
    ("kind", "content_type", "canonical_kind", "canonical_type", "normalized_attrs"),
    [
        ("biosample", "dna_stock", "bio_molecule_or_virus", "dna", {"state": "stock"}),
        ("formulation", "custom_lab_mix", "formulation", "other_formulation", {"original_type": "custom_lab_mix"}),
        ("chemical", "medium", "chemical", "other_chemical", {"original_type": "medium"}),
    ],
)
def test_content_taxonomy_compat_tokens_warn_and_preserve_runtime_metadata(
    quoted, kind, content_type, canonical_kind, canonical_type, normalized_attrs,
):
    kind_expr = f'"{kind}"' if quoted else kind
    type_expr = f'"{content_type}"' if quoted else content_type
    source = f'''
protocol T {{
  let x = tube(capacity = 5mL, load = [
    content(kind = {kind_expr}, type = {type_expr}, code = "M", attrs = {{ role: lab_specific_role }}):4mL
  ]);
}}
'''
    plan, diagnostics = _plan_from_source(source)
    assert [(d.code, d.severity) for d in diagnostics] == [
        ("SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED", "warning")
    ]
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    content = result.state.artifacts["material_state"]["content_registry"]["M"]
    assert content["content_kind"] == canonical_kind
    assert content["content_type"] == canonical_type
    assert content["content_original_kind"] == kind
    assert content["content_original_type"] == content_type
    assert content["content_attrs"] == {**normalized_attrs, "role": "lab_specific_role"}


@pytest.mark.parametrize("binding", ["local-string-alias", "parameter-default", "parameter-argument"])
def test_constructor_kind_bindings_remain_compatible(binding):
    params = ""
    declarations = ""
    entry_args = {}
    if binding == "local-string-alias":
        declarations = 'let family = "formulation"; let material_kind = family; let vessel_kind = "tube";'
    elif binding == "parameter-default":
        params = '(material_kind = "formulation", vessel_kind = "tube")'
    else:
        params = "(material_kind, vessel_kind)"
        entry_args = {"T": {"material_kind": "formulation", "vessel_kind": "tube"}}
    compiled = _compile_source(f'''
protocol T{params} {{
  {declarations}
  let x = container(kind = vessel_kind, capacity = 5mL, load = [
    content(kind = material_kind, type = medium, code = "M"):4mL
  ]);
}}
''')
    semantic = validate(
        compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict", enforce_binding=True,
    )
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert not semantic.diagnostics
    typed = typecheck(semantic.ir)
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(typed.ir, entry_args_by_protocol=entry_args)
    assert not plan.diagnostics
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    content = result.state.artifacts["material_state"]["content_registry"]["M"]
    assert content["content_kind"] == "formulation"
    assert content["content_type"] == "medium"


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
