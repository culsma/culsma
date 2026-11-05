"""Dimensions, aliases and scientific bounds are checked when statically known."""
from dataclasses import replace

import pytest

from culsma.pipeline.ir_nodes import IRQuantity
from culsma.pipeline.typecheck import typecheck


@pytest.mark.parametrize("name,value,code", [
    ("thermal", "22C", None), ("thermal", "295.15K", None),
    ("thermal", "1min", "TYPE_ENV_THERMAL_DIMENSION_MISMATCH"),
    ("duration", "1ms", None), ("duration", "1day", None),
    ("duration", "1mL", "TYPE_ENV_DURATION_DIMENSION_MISMATCH"),
    *[(name, value, code) for name in ("co2", "o2", "rh") for value, code in (
        ("5%", None), ("5pct", "TYPE_UNIT_LEGACY_ALIAS"),
        ("5", "TYPE_UNKNOWN_UNIT"), ("5min", "TYPE_ENV_PERCENT_DIMENSION_MISMATCH"),
        ('"5%"', "TYPE_ENV_PERCENT_DIMENSION_MISMATCH"),
    )],
])
def test_environment_dimensions(compile_source, env_source, name, value, code):
    args = {"thermal": "22C", "duration": "1min", name: value}
    compiled = compile_source(env_source(", ".join(f"{k}={v}" for k, v in args.items())))
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    assert result.ok == (code is None or code == "TYPE_UNIT_LEGACY_ALIAS")
    if code:
        assert code in [d.code for d in result.diagnostics]
        assert all(d.span is not None for d in result.diagnostics)


@pytest.mark.parametrize("args,code", [
    ("thermal=-273.15C, duration=1s", None),
    ("thermal=0K, duration=1s", None),
    ("thermal=-273.16C, duration=1s", "TYPE_ENV_VALUE_OUT_OF_RANGE"),
    ("thermal=-1K, duration=1s", "TYPE_ENV_VALUE_OUT_OF_RANGE"),
    ("thermal=22C, duration=0s", "TYPE_ENV_VALUE_OUT_OF_RANGE"),
    ("thermal=22C, duration=-1min", "TYPE_ENV_VALUE_OUT_OF_RANGE"),
    *[(f"thermal=22C, duration=1s, {name}={value}", code)
      for name in ("co2", "o2", "rh") for value, code in (
          ("0%", None), ("100%", None),
          ("-1%", "TYPE_ENV_VALUE_OUT_OF_RANGE"), ("100.1%", "TYPE_ENV_VALUE_OUT_OF_RANGE"))],
    ("thermal=22C, duration=1s, co2=20%, o2=80%", None),
    ("thermal=22C, duration=1s, co2=21%, o2=80%", "TYPE_ENV_GAS_TOTAL_OUT_OF_RANGE"),
])
def test_environment_bounds(compile_source, env_source, args, code):
    compiled = compile_source(env_source(args))
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    assert result.ok == (code is None), result.diagnostics
    if code:
        assert code in [d.code for d in result.diagnostics]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("name", ["thermal", "duration", "co2", "o2", "rh"])
def test_nonfinite_ir_is_rejected(compile_source, env_source, name, value):
    compiled = compile_source(env_source("thermal=22C, duration=1s, co2=5%, o2=20%, rh=80%"))
    env = compiled.ir.protocols[0].statements[-1]
    arg = next(arg for arg in env.env_args if arg.name == name)
    env.env_args[env.env_args.index(arg)] = replace(arg, value=IRQuantity(value, arg.value.unit))
    result = typecheck(compiled.ir)
    assert "TYPE_QUANTITY_VALUE_NONFINITE" in [d.code for d in result.diagnostics]


def test_bound_arithmetic_obeys_same_bounds(compile_source, env_source):
    source = env_source("thermal=22C, duration=1s, o2=oxygen")
    source = source.replace("with env", "let oxygen=80% + 25%; with env")
    result = typecheck(compile_source(source).ir)
    assert "TYPE_ENV_VALUE_OUT_OF_RANGE" in [d.code for d in result.diagnostics]
