"""Source-level agitation regressions, using the real frontend."""

from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate as _validate


def _compile_source(source):
    return compile_ast(resolve_program(parse(source)).prepared_program).ir


def validate(ir):
    return _validate(ir, analysis=build_compile_analysis(ir))


def _codes(result):
    return [diagnostic.code for diagnostic in result.diagnostics]


def test_validate_agit_accepts_shake_duration_rate():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = shake, duration = 30s, rate = 800rpm);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_MODE_UNKNOWN" not in _codes(result)
    assert "SEM_AGIT_ARG_CONFLICT" not in _codes(result)


def test_validate_agit_rejects_invert_with_duration():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = invert, duration = 30s);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_ARG_CONFLICT" in _codes(result)


def test_validate_agit_accepts_flick_with_optional_cycles():
    for cycle_arg in ("", ", cycles = 3"):
        src = f"""
protocol T {{
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = flick{cycle_arg});
}}
"""
        ir = _compile_source(src)
        result = validate(ir)
        assert "SEM_AGIT_MODE_UNKNOWN" not in _codes(result)
        assert "SEM_AGIT_ARG_CONFLICT" not in _codes(result)


def test_validate_agit_rejects_flick_with_duration_or_rate():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = flick, duration = 3s, rate = 60rpm);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert [d.code for d in result.diagnostics].count("SEM_AGIT_ARG_CONFLICT") == 2


def test_validate_agit_rejects_shake_with_cycles():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = shake, cycles = 10);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_ARG_CONFLICT" in _codes(result)


def test_validate_agit_rejects_unknown_mode():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = spin, duration = 30s);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_MODE_UNKNOWN" in _codes(result)
