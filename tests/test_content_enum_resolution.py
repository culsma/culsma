"""Phase 2A: explicit enum inputs through binding, semantic and type checking."""

from __future__ import annotations

import pytest

from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate


def check_source(source: str):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict", enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return semantic, typed


@pytest.mark.parametrize("binding", ["direct", "alias", "default", "deferred"])
def test_content_enum_inputs(binding):
    params, declarations = "", ""
    kind, content_type, container = "ContentKind.FORMULATION", "ContentType.MEDIUM", "ContainerKind.TUBE"
    if binding == "alias":
        declarations = f"let family = {kind}; let k = family; let t = {content_type}; let vessel = {container};"
        kind, content_type, container = "k", "t", "vessel"
    elif binding == "default":
        params = f"(k = {kind}, t = {content_type}, vessel = {container})"
        kind, content_type, container = "k", "t", "vessel"
    elif binding == "deferred":
        params = "(k, t, vessel)"
        kind, content_type, container = "k", "t", "vessel"
    semantic, typed = check_source(f'''protocol T{params} {{
      {declarations}
      let x = container(kind = {container}, load = [content(kind = {kind}, type = {content_type}):4mL]);
    }}''')
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]


@pytest.mark.parametrize(
    ("kind", "content_type", "semantic_code", "type_code"),
    [
        ("ContentKind.FORMULATON", "ContentType.MEDIUM", "SEM_CONTENT_ENUM_MEMBER_INVALID", None),
        ("ContentKind.FORMULATION", "ContentType.MEDUIM", "SEM_CONTENT_ENUM_MEMBER_INVALID", None),
        ("ContentType.MEDIUM", "ContentType.MEDIUM", None, "TYPE_CONTENT_ENUM_TYPE_MISMATCH"),
        ("ContentKind.FORMULATION", "ContentKind.FORMULATION", None, "TYPE_CONTENT_ENUM_TYPE_MISMATCH"),
        ("ContentKind.CHEMICAL", "ContentType.MEDIUM", "SEM_INVALID_CONTENT_TYPE_VALUE", None),
    ],
)
def test_content_enum_diagnostic_ownership(kind, content_type, semantic_code, type_code):
    semantic, typed = check_source(f'''protocol T {{
      let x = tube(load = [content(kind = {kind}, type = {content_type}):4mL]);
    }}''')
    assert [d.code for d in semantic.diagnostics] == ([] if semantic_code is None else [semantic_code])
    assert [d.code for d in typed.diagnostics] == ([] if type_code is None else [type_code])


def test_enum_namespace_is_not_an_unbound_alias_root():
    semantic, typed = check_source('protocol T { let k = ContentKind.FORMULATON; }')
    assert [d.code for d in semantic.diagnostics] == ["SEM_CONTENT_ENUM_MEMBER_INVALID"]
    assert typed.ok


def test_unused_parameter_default_checks_enum_members():
    semantic, typed = check_source('protocol T(k=ContentKind.FORMULATON) { }')
    assert [d.code for d in semantic.diagnostics] == ["SEM_CONTENT_ENUM_MEMBER_INVALID"]
    assert typed.ok


def test_enum_assignment_captures_value_before_other_binding_changes():
    semantic, typed = check_source('''protocol T {
      let k=ContentKind.CHEMICAL;
      let other=ContentKind.FORMULATION;
      k=other;
      other=ContentKind.CHEMICAL;
      let x=tube(load=[content(kind=k, type=ContentType.MEDIUM):4mL]);
    }''')
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]


def test_content_enum_family_through_alias():
    semantic, typed = check_source('''protocol T {
      let k = ContentType.MEDIUM;
      let x = tube(load = [content(kind = k, type = ContentType.MEDIUM):4mL]);
    }''')
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert [d.code for d in typed.diagnostics] == ["TYPE_CONTENT_ENUM_TYPE_MISMATCH"]


def test_enum_surface_still_forbids_capacity():
    semantic, _ = check_source('protocol T { let x = container(kind = ContainerKind.SURFACE, capacity = 5mL); }')
    assert [d.code for d in semantic.diagnostics] == ["SEM_SURFACE_CAPACITY_FORBIDDEN"]


@pytest.mark.parametrize("use_alias", [False, True])
def test_frontend_enum_support_cannot_silently_execute_empty_classification(use_alias):
    from culsma.pipeline.plan import lower_ir_to_plan
    from culsma.driver.stub import StubDriver
    from culsma.runtime.executor import run

    declarations = "let k = ContentKind.FORMULATION;" if use_alias else ""
    kind = "k" if use_alias else "ContentKind.FORMULATION"
    source = f'''protocol T {{ {declarations}
      let x = tube(capacity=5mL, load=[content(kind={kind}, type=ContentType.MEDIUM, code="M"):4mL]);
    }}'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    plan = lower_ir_to_plan(compiled.ir)
    assert [d.code for d in plan.diagnostics] == ["PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED"]
    assert plan.plans == []
    result = run(plan=plan, driver=StubDriver())
    assert not result.ok
    assert not result.state.artifacts.get("material_state", {}).get("content_registry")


@pytest.mark.parametrize("namespace", ['let ContentKind = "shadow";', ''])
def test_namespace_shadowing_is_not_reinterpreted_as_builtin(namespace):
    params = "" if namespace else '(ContentKind = "shadow")'
    semantic, typed = check_source(f'''protocol T{params} {{ {namespace}
      let x = tube(load=[content(kind=ContentKind.FORMULATION, type=ContentType.MEDIUM):4mL]);
    }}''')
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert [d.code for d in typed.diagnostics] == ["TYPE_CONTENT_KIND_NOT_TEXT"]


@pytest.mark.parametrize("selected", ["saved", "k"])
def test_enum_alias_keeps_value_when_original_binding_changes(selected):
    semantic, typed = check_source(f'''protocol T {{
      let k = ContentKind.FORMULATION;
      let saved = k;
      k = ContentKind.CHEMICAL;
      let x = tube(load=[content(kind={selected}, type=ContentType.MEDIUM):4mL]);
    }}''')
    assert [d.code for d in semantic.diagnostics] == ([] if selected == "saved" else ["SEM_INVALID_CONTENT_TYPE_VALUE"])
    assert typed.ok


@pytest.mark.parametrize("kind", ["ContentKind.CHEMICAL", "chemical"])
def test_explicit_enum_pair_errors_never_fall_back_in_compat_mode(kind):
    source = f'protocol T {{ let x = tube(load=[content(kind={kind}, type=ContentType.MEDIUM):4mL]); }}'
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="compat")
    assert [d.code for d in semantic.diagnostics] == ["SEM_INVALID_CONTENT_TYPE_VALUE"]


@pytest.mark.parametrize("kind", ["ContentKind.BIO_CELLULAR", "ContentKind.FORMULATION"])
def test_cell_count_checks_resolve_content_enum_kind(kind):
    content_type = "ContentType.CELL_LINE" if "BIO_CELLULAR" in kind else "ContentType.MEDIUM"
    _, typed = check_source(f'protocol T {{ let x=tube(load=[content(kind={kind}, type={content_type}):4cells]); }}')
    assert [d.code for d in typed.diagnostics] == ([] if "BIO_CELLULAR" in kind else ["TYPE_LOAD_COUNT_CONTENT_MISMATCH"])


def test_assignment_cannot_change_enum_family():
    _, typed = check_source('protocol T { let k=ContentKind.FORMULATION; k=ContentType.MEDIUM; }')
    assert [d.code for d in typed.diagnostics] == ["TYPE_LOCAL_ASSIGN_MISMATCH"]


def test_cell_count_observes_latest_enum_assignment():
    semantic, typed = check_source('''protocol T {
      let k=ContentKind.FORMULATION;
      k=ContentKind.BIO_CELLULAR;
      let x=tube(load=[content(kind=k, type=ContentType.CELL_LINE):4cells]);
    }''')
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
