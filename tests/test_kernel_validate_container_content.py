from __future__ import annotations

import pytest

from culsma.pipeline.analysis import build_compile_analysis
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRProgram, IRProtocol, IRQuantity, IRStep, IRString
from culsma.pipeline.validate import validate as _validate
from culsma.pipeline.compat.content_syntax import resolve_kind_token


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def validate(ir, **kwargs):
    kwargs.setdefault("analysis", build_compile_analysis(ir))
    return _validate(ir, **kwargs)


def _ir_step(name: str, args: list[IRArg]) -> IRProgram:
    return IRProgram(protocols=[IRProtocol(id="p0", name="T", statements=[IRStep(id="p0.s0", name=name, args=args)])])


@pytest.mark.parametrize(
    ("value", "literal_bindings", "defined_names", "expected"),
    [
        pytest.param(None, {}, set(), None, id="missing-kind"),
        pytest.param(IRString("formulation"), {}, set(), "formulation", id="quoted-kind"),
        pytest.param(IRIdentifier("formulation"), {}, set(), "formulation", id="bare-kind"),
        pytest.param(IRIdentifier("formulaton"), {}, set(), "formulaton", id="typo-reaches-whitelist"),
        pytest.param(IRIdentifier("family"), {"family": "formulation"}, {"family"}, "formulation", id="string-binding"),
        pytest.param(IRIdentifier("formulation"), {"formulation": "chemical"}, {"formulation"}, "chemical", id="binding-before-spelling"),
        pytest.param(IRIdentifier("family"), {}, {"family"}, None, id="declared-parameter-is-not-token"),
        pytest.param(IRIdentifier("formulation"), {}, {"formulation"}, None, id="deferred-binding-shadows-token"),
        pytest.param(IRIdentifier("formulation"), {"formulation": 5}, set(), None, id="nontext-binding-is-not-token"),
        pytest.param(IRQuantity(5, None), {}, set(), None, id="nontext-expression-is-not-token"),
    ],
)
def test_resolve_kind_token_preserves_literal_and_binding_distinction(value, literal_bindings, defined_names, expected):
    """The public resolver distinguishes candidate tokens from existing bindings."""
    arg = IRArg(name="kind", value=value) if value is not None else None
    assert resolve_kind_token(arg, literal_bindings, defined_names) == expected


@pytest.mark.parametrize("quote_kind", [False, True], ids=["bare-kind", "quoted-kind"])
@pytest.mark.parametrize("quote_type", [False, True], ids=["bare-type", "quoted-type"])
@pytest.mark.parametrize(
    ("kind", "content_type", "expected_code"),
    [
        pytest.param("formulation", "medium", None, id="valid-medium"),
        pytest.param("formulaton", "medium", "SEM_INVALID_CONTENT_KIND", id="misspelled-kind"),
        pytest.param("chemical", "medium", "SEM_INVALID_CONTENT_TYPE_VALUE", id="wrong-kind-type-pair"),
        pytest.param("formulation", "meduim", "SEM_INVALID_CONTENT_TYPE_VALUE", id="misspelled-type"),
    ],
)
def test_source_content_taxonomy_strict_validation(kind, content_type, expected_code, quote_kind, quote_type):
    """PM #110: source spelling must not bypass CF-CNT-001/002 validation."""
    kind_expr = f'"{kind}"' if quote_kind else kind
    type_expr = f'"{content_type}"' if quote_type else content_type
    source = f'''
protocol T {{
  let x = tube(label = "X", capacity = 5mL, load = [
    content(kind = {kind_expr}, type = {type_expr}, code = "DMEM_F12_COMPLETE", attrs = {{ role: culture }}):4mL
  ]);
}}
'''
    frontend = resolve_program(parse(source))
    compiled = compile_ast(frontend.prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict")
    if expected_code is None:
        assert result.ok, [d.to_dict() for d in result.diagnostics]
        assert not result.diagnostics
    else:
        assert expected_code in _codes(result), (
            f"Expected {expected_code} for kind={kind_expr}, type={type_expr}; "
            f"got ok={result.ok}, diagnostics={_codes(result)}"
        )
        assert not result.ok


@pytest.mark.parametrize("quote_kind", [False, True], ids=["bare-kind", "quoted-kind"])
@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        pytest.param("tube", None, id="valid-tube"),
        pytest.param("cartridge", "SEM_INVALID_CONTAINER_KIND", id="unsupported-container-kind"),
    ],
)
def test_source_container_kind_strict_validation(kind, expected_code, quote_kind):
    """PM #110: CF-CNT-001 applies to both bare and quoted container kinds."""
    kind_expr = f'"{kind}"' if quote_kind else kind
    source = f'protocol T {{ let x = container(kind = {kind_expr}, label = "X"); }}'
    frontend = resolve_program(parse(source))
    compiled = compile_ast(frontend.prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict")
    if expected_code is None:
        assert result.ok, [d.to_dict() for d in result.diagnostics]
        assert not result.diagnostics
    else:
        assert expected_code in _codes(result), (
            f"Expected {expected_code} for kind={kind_expr}; "
            f"got ok={result.ok}, diagnostics={_codes(result)}"
        )
        assert not result.ok


@pytest.mark.parametrize("mode", ["strict", "compat"])
@pytest.mark.parametrize("kind", ["formulaton", '"formulaton"'])
def test_unknown_content_kind_is_rejected_in_both_modes(mode, kind):
    source = f'protocol T {{ let x = tube(load = [content(kind = {kind}, type = medium):4mL]); }}'
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode=mode)
    assert not result.ok
    assert _codes(result) == ["SEM_INVALID_CONTENT_KIND"]


@pytest.mark.parametrize("kind", ["surface", '"surface"', "surface_kind"])
def test_source_surface_kind_forbids_capacity(kind):
    source = f'''
protocol T {{
  let surface_kind = "surface";
  let x = container(kind = {kind}, capacity = 5mL);
}}
'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict")
    assert not result.ok
    assert _codes(result) == ["SEM_SURFACE_CAPACITY_FORBIDDEN"]


def test_source_content_kind_uses_bound_string_before_token_spelling():
    source = '''
protocol T {
  let formulation = "chemical";
  let x = tube(load = [content(kind = formulation, type = medium):4mL]);
}
'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict")
    assert not result.ok
    assert _codes(result) == ["SEM_INVALID_CONTENT_TYPE_VALUE"]
    assert "for kind 'chemical'" in result.diagnostics[0].message


@pytest.mark.parametrize(
    ("descriptor", "expected_code"),
    [
        ("container(kind = vessel_kind)", None),
        ("container(kind = cartridge)", "SEM_INVALID_CONTAINER_KIND"),
        ("container(load = [content(kind = material_kind, type = medium):4mL])", None),
        ("container(load = [content(kind = formulaton, type = medium):4mL])", "SEM_INVALID_CONTENT_KIND"),
    ],
)
def test_constraint_option_expression_preserves_constructor_scope(descriptor, expected_code):
    """Constraint option traversal must retain scope, independently of schema typing."""
    source = f'''
protocol T(vessel_kind, material_kind) {{
  with constraint(customized, schema_ref = {descriptor}) {{
    let x = tube();
  }}
}}
'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode="strict")
    assert _codes(result) == ([] if expected_code is None else [expected_code])


@pytest.mark.parametrize("token", [IRString, IRIdentifier], ids=["string", "bare"])
def test_container_kind_whitelist(token):
    """CF-CNT-001: constructor container kind whitelist is enforced."""
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=token("cartridge")),
            IRArg(name="label", value=IRString("C1")),
        ],
    )
    result = validate(ir, content_whitelist_mode="strict")
    assert "SEM_INVALID_CONTAINER_KIND" in _codes(result)


def test_container_kind_whitelist_accepts_surface_and_chamber():
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=IRString("surface")),
            IRArg(name="label", value=IRString("S1")),
        ],
    )
    result = validate(ir, content_whitelist_mode="strict")
    assert "SEM_INVALID_CONTAINER_KIND" not in _codes(result)

    ir2 = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=IRString("chamber")),
            IRArg(name="label", value=IRString("C1")),
        ],
    )
    result2 = validate(ir2, content_whitelist_mode="strict")
    assert "SEM_INVALID_CONTAINER_KIND" not in _codes(result2)


@pytest.mark.parametrize("token", [IRString, IRIdentifier], ids=["string", "bare"])
def test_surface_constructor_forbids_capacity(token):
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=token("surface")),
            IRArg(name="label", value=IRString("S1")),
            IRArg(name="capacity", value=IRQuantity(50.0, "uL")),
        ],
    )
    result = validate(ir, content_whitelist_mode="strict")
    assert "SEM_SURFACE_CAPACITY_FORBIDDEN" in _codes(result)


def test_container_label_is_optional():
    """Container constructors do not require a label when kind is present."""
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=IRString("tube")),
            IRArg(name="capacity", value=IRQuantity(50.0, "uL")),
        ],
    )
    result = validate(ir, content_whitelist_mode="strict")
    assert "SEM_MISSING_REQUIRED_ARG" not in _codes(result)


@pytest.mark.parametrize("token", [IRString, IRIdentifier], ids=["string", "bare"])
def test_content_kind_whitelist(token):
    """CF-CNT-001: constructor content kind whitelist is enforced."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=token("unknown_kind")),
            IRArg(name="name", value=IRString("X")),
        ],
    )
    result = validate(ir, content_whitelist_mode="strict")
    assert "SEM_INVALID_CONTENT_KIND" in _codes(result)


def test_content_type_required_mode():
    """CF-CNT-002: required policy enforces content_type presence/format."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" in _codes(result)


def test_content_type_required_by_default_baseline():
    """CF-CNT-002: public baseline defaults to required content_type enforcement."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir)
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" in _codes(result)


def test_content_type_standard_bare_token_is_allowed():
    """Standard content_type tokens may be authored as bare identifiers."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("bio_fluid")),
            IRArg(name="type", value=IRIdentifier("whole_blood")),
            IRArg(name="name", value=IRString("S1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" not in _codes(result)
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" not in _codes(result)


def test_content_type_standard_string_form_is_still_allowed():
    """String form of a canonical content_type token still passes."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("formulation")),
            IRArg(name="type", value=IRString("buffer")),
            IRArg(name="name", value=IRString("B1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" not in _codes(result)
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" not in _codes(result)


def test_content_type_unknown_value_is_compat_warning_by_default():
    """v1.0.2 compatibility accepts unknown legacy values with a warning."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="type", value=IRIdentifier("my_lab_mix")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert result.ok
    assert "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED" in _codes(result)


def test_content_type_unknown_value_is_rejected_in_strict_mode():
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="type", value=IRIdentifier("my_lab_mix")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir, content_type_policy="required", content_whitelist_mode="strict")
    assert "SEM_INVALID_CONTENT_KIND" in _codes(result)


def test_content_type_legacy_biosample_dna_warns_and_normalizes():
    """Legacy biosample/dna is accepted as compatibility input."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("biosample")),
            IRArg(name="type", value=IRIdentifier("dna")),
            IRArg(name="name", value=IRString("DNA")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert result.ok
    assert "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED" in _codes(result)


def test_content_type_compat_warning_suggests_canonical_content_form_with_attrs():
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("biosample")),
            IRArg(name="type", value=IRIdentifier("dna_stock")),
            IRArg(name="name", value=IRString("DNA")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    warning = next(d for d in result.diagnostics if d.code == "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED")
    assert 'content(kind="bio_molecule_or_virus", type="dna", attrs={state: "stock"})' in warning.message
    assert "Use that canonical content form to avoid this warning." in warning.message


def test_content_type_custom_prefix_is_compat_warning():
    """custom_* is compatibility input, not current canonical public vocabulary."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="type", value=IRIdentifier("custom_my_lab_mix")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" not in _codes(result)
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" not in _codes(result)
    assert "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED" in _codes(result)


def test_inline_content_taxonomy_compat_warning_is_not_duplicated():
    src = '''
protocol T {
  let x = tube(label = "X", load = [content(kind = "biosample", type = "dna_stock", code = "DNA1"):10uL]);
}
'''
    frontend = resolve_program(parse(src))
    compiled = compile_ast(frontend.prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis)
    warnings = [d for d in result.diagnostics if d.code == "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED"]
    assert result.ok
    assert len(warnings) == 1


def test_content_family_sugar_warns_through_taxonomy_compat_path():
    src = '''
protocol T {
  let x = tube(label = "X", load = [
    blood(code = "B1"):10uL,
    buffer(code = "BUF", type = "wash_buffer"):10uL,
    reagent(code = "R1", type = "cleanup_reagent"):10uL
  ]);
}
'''
    frontend = resolve_program(parse(src))
    compiled = compile_ast(frontend.prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis)
    warnings = [d for d in result.diagnostics if d.code == "SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED"]
    assert result.ok
    assert len(warnings) == 3


def test_constructor_shape_errors_are_semantic():
    """CF-CNT-004: constructor shape/whitelist failures are owned by semantic stage."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="name", value=IRString("S")),
            IRArg(name="code", value=IRQuantity(5.0, "uL")),
        ],
    )
    result = validate(ir)
    codes = _codes(result)
    assert "SEM_MISSING_CONTENT_KIND" in codes
    assert not any(code.startswith("TYPE_") for code in codes)
