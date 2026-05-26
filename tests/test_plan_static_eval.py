from __future__ import annotations

import pytest

from culsma.pipeline.plan.static_eval import PlanStaticEvaluator


def q(value: float, unit: str | None = None) -> dict:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def b(value: bool) -> dict:
    return {"kind": "IRBoolean", "value": value, "span": None}


def s(value: str) -> dict:
    return {"kind": "IRString", "value": value, "span": None}


def ident(name: str) -> dict:
    return {"kind": "IRIdentifier", "name": name, "span": None}


def arg(name: str, value: object) -> dict:
    return {"name": name, "value": value, "span": None}


def call(name: str, args: list[dict]) -> dict:
    return {"kind": "IRCall", "name": name, "args": args, "span": None}


def binary(op: str, left: object, right: object) -> dict:
    return {"kind": "IRBinary", "op": op, "left": left, "right": right, "span": None}


def unary(op: str, operand: object) -> dict:
    return {"kind": "IRUnary", "op": op, "operand": operand, "span": None}


def test_schedule_payload_args_and_modes_are_public_static_eval_api():
    evaluator = PlanStaticEvaluator()
    schedule = call("schedule", [arg("start", q(1)), arg("step", q(1)), arg("mode", ident("continuous"))])

    assert evaluator.is_schedule_payload(schedule)
    assert not evaluator.is_schedule_payload(call("other", []))
    args = evaluator.schedule_args(schedule)
    assert args["start"] == q(1)
    assert evaluator.schedule_mode_from_args({}) == "discrete"
    assert evaluator.schedule_mode_from_args({"mode": s("continuous")}) == "continuous"
    assert evaluator.schedule_mode(schedule) == "continuous"
    with pytest.raises(ValueError, match="schedule mode"):
        evaluator.schedule_mode_from_args({"mode": s("bad")})
    with pytest.raises(ValueError, match="args must be a list"):
        evaluator.schedule_args({"kind": "IRCall", "name": "schedule", "args": {}})


def test_numeric_and_boolean_static_expr_methods_are_directly_tested():
    evaluator = PlanStaticEvaluator()

    assert evaluator.try_eval_numeric_expr(binary("+", q(2), unary("-", q(1)))) == 1
    assert evaluator.try_eval_numeric_expr(q(2, "min")) is None
    assert evaluator.compare_values(2, 3, "<")
    with pytest.raises(ValueError, match="unsupported comparison"):
        evaluator.compare_values(2, 3, "contains")

    assert evaluator.try_eval_bool_expr(binary("and", b(True), binary(">", q(3), q(2)))) is True
    assert evaluator.eval_bool(binary("==", b(True), b(False))) is False
    assert evaluator.try_eval_bool_expr(ident("runtime_flag")) is None


def test_quantity_and_point_helpers_are_public_static_eval_api():
    evaluator = PlanStaticEvaluator()

    assert evaluator.plan_quantity(binary("*", q(2), q(3))) == {"value": 6.0, "unit": None, "span": None}
    minute = evaluator.plan_quantity(q(2, "min"))
    unitless = evaluator.plan_quantity(q(3))
    assert evaluator.is_time_point(minute)
    assert evaluator.is_unitless_int_point(unitless)
    assert evaluator.time_quantity_to_seconds(minute) == 120
    assert evaluator.seconds_to_unit(120, "min") == 2
    assert evaluator.quantity_payload(minute) == q(2.0, "min")

    evaluator.validate_schedule_point_list([minute, evaluator.plan_quantity(q(3, "min"))])
    with pytest.raises(ValueError, match="consistent types"):
        evaluator.validate_schedule_point_list([minute, unitless])

    evaluator.validate_points_within_boundary([minute], q(3, "min"))
    with pytest.raises(ValueError, match="exceeds enclosing env boundary"):
        evaluator.validate_points_within_boundary([evaluator.plan_quantity(q(4, "min"))], q(3, "min"))

    evaluator.validate_boundary_within_env(minute, q(3, "min"), message="too long")
    with pytest.raises(ValueError, match="too long"):
        evaluator.validate_boundary_within_env(evaluator.plan_quantity(q(4, "min")), q(3, "min"), message="too long")


def test_schedule_point_expansion_methods_are_public_static_eval_api():
    evaluator = PlanStaticEvaluator()

    time_points = evaluator.expand_time_schedule_points(
        evaluator.plan_quantity(q(0, "min")),
        evaluator.plan_quantity(q(2, "min")),
        evaluator.plan_quantity(q(1, "min")),
    )
    assert [point["value"] for point in time_points] == [0, 1, 2]

    count_points = evaluator.expand_count_schedule_points(
        evaluator.plan_quantity(q(1)),
        evaluator.plan_quantity(q(3)),
        evaluator.plan_quantity(q(1)),
    )
    assert [point["value"] for point in count_points] == [1, 2, 3]

    with pytest.raises(ValueError, match="time step"):
        evaluator.expand_time_schedule_points(
            evaluator.plan_quantity(q(0, "min")),
            evaluator.plan_quantity(q(2, "min")),
            evaluator.plan_quantity(q(0, "min")),
        )
    with pytest.raises(ValueError, match="count step"):
        evaluator.expand_count_schedule_points(
            evaluator.plan_quantity(q(1)),
            evaluator.plan_quantity(q(3)),
            evaluator.plan_quantity(q(0)),
        )


def test_discrete_schedule_evaluation_uses_public_component_methods():
    evaluator = PlanStaticEvaluator()

    explicit = call(
        "schedule",
        [arg("at", {"kind": "IRList", "elements": [q(1, "min"), q(2, "min")], "span": None})],
    )
    assert [point["value"] for point in evaluator.eval_discrete_schedule_points(explicit)] == [1, 2]

    interval = call("schedule", [arg("start", q(1)), arg("end", q(3)), arg("step", q(1))])
    assert [point["value"] for point in evaluator.eval_discrete_schedule_points(interval)] == [1, 2, 3]

    repeat_count_args = evaluator.schedule_args(
        call("schedule", [arg("start", q(1)), arg("end", q(2)), arg("step", q(1)), arg("__repeat_count", b(True))])
    )
    assert evaluator.is_repeat_count_schedule(repeat_count_args)


def test_continuous_schedule_and_env_boundary_methods_are_public_static_eval_api():
    evaluator = PlanStaticEvaluator()

    continuous = call(
        "schedule",
        [arg("start", q(15, "min")), arg("end", q(45, "min")), arg("mode", s("continuous"))],
    )
    assert evaluator.eval_continuous_schedule_boundary(continuous) == q(30.0, "min")

    duration_schedule = call(
        "schedule",
        [arg("start", q(0, "min")), arg("duration", q(2, "min")), arg("mode", s("continuous"))],
    )
    assert evaluator.eval_continuous_schedule_boundary(duration_schedule, env_time_boundary=q(3, "min")) == q(2.0, "min")

    env_payload = {"duration": q(5, "min")}
    assert evaluator.is_time_quantity_payload(env_payload["duration"])
    assert evaluator.env_time_boundary_from_payload(env_payload) == q(5, "min")

    thermal_payload = call("thermal_program", [arg("duration", q(6, "min"))])
    assert evaluator.env_time_boundary_from_payload({"thermal": thermal_payload}) == q(6, "min")
