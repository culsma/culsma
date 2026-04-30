from __future__ import annotations

from culsma.pipeline.analysis import build_compile_analysis
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
            IRArg(name="kind", value=IRString("biosample")),
            IRArg(name="type", value=IRIdentifier("whole_blood")),
            IRArg(name="name", value=IRString("S1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" not in _codes(result)
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" not in _codes(result)


def test_content_type_standard_string_form_is_still_allowed():
    """Compatibility string form of a standard content_type token still passes."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("buffer")),
            IRArg(name="type", value=IRString("lysis_buffer")),
            IRArg(name="name", value=IRString("B1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_FORMAT" not in _codes(result)
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" not in _codes(result)


def test_content_type_unknown_value_requires_custom_prefix():
    """Unknown content_type values must use the custom_ prefix."""
    ir = _ir_step(
        "DefineContent",
        [
            IRArg(name="kind", value=IRString("reagent")),
            IRArg(name="type", value=IRIdentifier("my_lab_mix")),
            IRArg(name="name", value=IRString("R1")),
        ],
    )
    result = validate(ir, content_type_policy="required")
    assert "SEM_INVALID_CONTENT_TYPE_VALUE" in _codes(result)


def test_content_type_custom_prefix_is_allowed():
    """Non-standard content_type values may use the custom_ prefix."""
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
