"""Environment vocabulary and combination rules belong to semantic validation."""
import pytest

from culsma.pipeline.validate import validate


@pytest.mark.parametrize("extra,code", [
    ("co2=5%, rh=80%", None), ("o2=20%", None),
    ("co2=5%, o2=20%, rh=80%", None),
    ("humidity=80%", "SEM_UNKNOWN_ARG"), ("shake=300rpm", "SEM_UNKNOWN_ARG"),
    ('device="incubator"', "SEM_UNKNOWN_ARG"),
    ("o2=20%, o2=10%", "SEM_DUPLICATE_ARG"),
])
def test_environment_names(compile_source, env_source, extra, code):
    compiled = compile_source(env_source(f"thermal=22C, duration=1min, {extra}"))
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert result.ok == (code is None)
    if code:
        assert code in [d.code for d in result.diagnostics]


@pytest.mark.parametrize("args,code", [
    ("field=mz_separation", None),
    ("co2=5%", "SEM_ENV_THERMAL_REQUIRED"),
    ("o2=20%", "SEM_ENV_THERMAL_REQUIRED"),
    ("field=mz_separation, o2=20%", "SEM_ENV_ARG_CONFLICT"),
    ("field=mz_separation, rh=80%", "SEM_ENV_ARG_CONFLICT"),
    ("field=mz_separation, duration=1min", "SEM_ENV_DURATION_WITHOUT_THERMAL"),
    ("duration=1min", "SEM_ENV_DURATION_WITHOUT_THERMAL"),
    ("thermal=22C", "SEM_ENV_DURATION_REQUIRED"),
    ("thermal=-20C", "SEM_ENV_DURATION_REQUIRED"),
    ("thermal=thermal_program(from=22C, duration=1min), o2=20%", "SEM_ENV_ARG_CONFLICT"),
    ("thermal=thermal_program(from=22C, duration=1min), rh=80%", "SEM_ENV_ARG_CONFLICT"),
    ("thermal=thermal_program(from=22C, duration=1min), duration=1min", "SEM_ENV_DURATION_FORBIDDEN_WITH_THERMAL_PROGRAM"),
])
def test_environment_combinations(compile_source, env_source, args, code):
    compiled = compile_source(env_source(args))
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert result.ok == (code is None)
    if code:
        assert code in [d.code for d in result.diagnostics]


def test_active_operation_does_not_gain_duration(compile_source, env_source):
    compiled = compile_source(env_source("thermal=22C, o2=20%", 'img(sample=sample, quantity=fluorescence);'))
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert result.ok, result.diagnostics


def test_untyped_thermal_parameter_defers_duration_decision(compile_source):
    compiled = compile_source('protocol T(temp) { let sample=tube(); with env(thermal=temp) { hold(sample); } }')
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert result.ok, result.diagnostics
