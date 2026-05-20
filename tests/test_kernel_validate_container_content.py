from __future__ import annotations

from culsma.pipeline.analysis import build_compile_analysis
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRProgram, IRProtocol, IRQuantity, IRStep, IRString
from culsma.pipeline.validate import validate as _validate


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def validate(ir, **kwargs):
    kwargs.setdefault("analysis", build_compile_analysis(ir))
    return _validate(ir, **kwargs)


def _ir_step(name: str, args: list[IRArg]) -> IRProgram:
    return IRProgram(protocols=[IRProtocol(id="p0", name="T", statements=[IRStep(id="p0.s0", name=name, args=args)])])


def test_container_kind_whitelist():
    """CF-CNT-001: constructor container kind whitelist is enforced."""
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=IRString("cartridge")),
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


def test_surface_constructor_forbids_capacity():
    ir = _ir_step(
        "AllocContainer",
        [
            IRArg(name="kind", value=IRString("surface")),
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


def test_content_kind_whitelist():
    """CF-CNT-001: constructor content kind whitelist is enforced."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("unknown_kind")),
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
