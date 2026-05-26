"""Plan-time static expression helpers."""

from __future__ import annotations

from typing import Any, Mapping

TIME_UNIT_SCALE = {
    "ms": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "hr": 3600.0,
    "h": 3600.0,
}


class PlanStaticEvaluator:
    def is_schedule_payload(self, value: Any) -> bool:
        return isinstance(value, dict) and value.get("kind") == "IRCall" and value.get("name") == "schedule"

    def schedule_args(self, schedule: Mapping[str, Any]) -> dict[str, Any]:
        raw_args = schedule.get("args")
        if not isinstance(raw_args, list):
            raise ValueError("schedule args must be a list")
        args: dict[str, Any] = {}
        for raw_arg in raw_args:
            if not isinstance(raw_arg, Mapping):
                raise ValueError("schedule args must be named values")
            name = raw_arg.get("name")
            if not isinstance(name, str):
                raise ValueError("schedule arg name must be a string")
            args[name] = raw_arg.get("value")
        return args

    def schedule_mode(self, schedule: Mapping[str, Any]) -> str:
        return self.schedule_mode_from_args(self.schedule_args(schedule))

    def schedule_mode_from_args(self, args: Mapping[str, Any]) -> str:
        raw = args.get("mode")
        if raw is None:
            return "discrete"
        if isinstance(raw, str) and raw in {"discrete", "continuous"}:
            return raw
        if isinstance(raw, Mapping):
            if raw.get("kind") == "IRString" and raw.get("value") in {"discrete", "continuous"}:
                return str(raw["value"])
            if raw.get("kind") == "IRIdentifier" and raw.get("name") in {"discrete", "continuous"}:
                return str(raw["name"])
        raise ValueError("schedule mode must be discrete or continuous")

    def eval_bool(self, value: Any) -> bool | None:
        return self.try_eval_bool_expr(value)

    def try_eval_bool_expr(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return bool(value)
        if not isinstance(value, Mapping):
            return None
        kind = value.get("kind")
        if kind == "IRBoolean":
            return bool(value.get("value"))
        if kind == "IRBinary":
            op = value.get("op")
            if op in {"and", "or"}:
                left = self.try_eval_bool_expr(value.get("left"))
                right = self.try_eval_bool_expr(value.get("right"))
                if left is None or right is None:
                    return None
                return (left and right) if op == "and" else (left or right)
            if op in {"==", "!=", "<", ">", "<=", ">="}:
                left_num = self.try_eval_numeric_expr(value.get("left"))
                right_num = self.try_eval_numeric_expr(value.get("right"))
                if left_num is not None and right_num is not None:
                    return self.compare_values(left_num, right_num, op)
                left_bool = self.try_eval_bool_expr(value.get("left"))
                right_bool = self.try_eval_bool_expr(value.get("right"))
                if left_bool is not None and right_bool is not None and op in {"==", "!="}:
                    return (left_bool == right_bool) if op == "==" else (left_bool != right_bool)
        return None

    def try_eval_numeric_expr(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, Mapping):
            return None
        kind = value.get("kind")
        if kind == "IRQuantity":
            if value.get("unit") is not None or not isinstance(value.get("value"), (int, float)):
                return None
            return float(value["value"])
        if kind == "IRUnary":
            operand = self.try_eval_numeric_expr(value.get("operand"))
            if operand is None:
                return None
            return -operand if value.get("op") == "-" else None
        if kind == "IRBinary":
            left = self.try_eval_numeric_expr(value.get("left"))
            right = self.try_eval_numeric_expr(value.get("right"))
            if left is None or right is None:
                return None
            op = value.get("op")
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                if right == 0:
                    raise ValueError("repeat count expression division by zero")
                return left / right
        return None

    def compare_values(self, left: float, right: float, op: Any) -> bool:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
        raise ValueError(f"unsupported comparison operator: {op}")

    def eval_discrete_schedule_points(
        self,
        schedule: Mapping[str, Any],
        *,
        env_time_boundary: Any = None,
    ) -> list[dict[str, Any]]:
        args = self.schedule_args(schedule)
        mode = self.schedule_mode_from_args(args)
        if mode != "discrete":
            raise ValueError("only discrete schedule can be expanded as static repeat points")
        if "duration" in args or "observe_every" in args or "control_every" in args:
            raise ValueError("discrete schedule does not allow duration, observe_every, or control_every")
        has_at = "at" in args
        has_interval_shape = any(name in args for name in {"start", "step", "end"})
        if has_at == has_interval_shape:
            raise ValueError("schedule(...) must use either start/end/step or at=[...]")
        if has_at:
            raw_points = args["at"]
            if not isinstance(raw_points, Mapping) or raw_points.get("kind") != "IRList":
                raise ValueError("schedule(at=[...]) requires a list")
            elements = raw_points.get("elements")
            if not isinstance(elements, list) or not elements:
                raise ValueError("schedule(at=[...]) requires non-empty list")
            points = [self.plan_quantity(point) for point in elements]
            self.validate_schedule_point_list(points)
            self.validate_points_within_boundary(points, env_time_boundary)
            return [self.quantity_payload(point) for point in points]

        if "start" not in args or "step" not in args:
            raise ValueError("schedule(start=..., step=...) requires start and step")
        effective_end = args.get("end")
        start = self.plan_quantity(args["start"])
        step = self.plan_quantity(args["step"])
        if effective_end is None:
            if not self.is_time_point(start):
                raise ValueError("count schedule requires explicit end")
            if env_time_boundary is None:
                raise ValueError("time schedule without end requires enclosing env boundary")
            effective_end = env_time_boundary
        end = self.plan_quantity(effective_end)
        if self.is_repeat_count_schedule(args):
            if end["value"] < 0:
                raise ValueError("repeat count must be >= 0")
            if not float(end["value"]).is_integer():
                raise ValueError("repeat count must be an integer")
        if self.is_time_point(start):
            if not self.is_time_point(step) or not self.is_time_point(end):
                raise ValueError("schedule start/end/step types must be consistent")
            return [
                self.quantity_payload(point)
                for point in self.expand_time_schedule_points(start, end, step, env_time_boundary)
            ]
        if self.is_unitless_int_point(start):
            if not self.is_unitless_int_point(step) or not self.is_unitless_int_point(end):
                raise ValueError("schedule start/end/step types must be consistent")
            return [self.quantity_payload(point) for point in self.expand_count_schedule_points(start, end, step)]
        raise ValueError("schedule(...) supports only time quantities or unitless integer points")

    def eval_continuous_schedule_boundary(
        self,
        schedule: Mapping[str, Any],
        *,
        env_time_boundary: Any = None,
    ) -> dict[str, Any]:
        args = self.schedule_args(schedule)
        mode = self.schedule_mode_from_args(args)
        if mode != "continuous":
            raise ValueError("continuous schedule boundary requires mode=continuous")
        if "at" in args or "step" in args:
            raise ValueError("schedule(mode=continuous) does not allow at or step")
        start = self.plan_quantity(args.get("start"))
        if not self.is_time_point(start):
            raise ValueError("schedule(mode=continuous) requires time-valued start")
        duration = args.get("duration")
        end = args.get("end")
        if duration is None and end is None:
            raise ValueError("schedule(mode=continuous) requires end or duration")
        if duration is not None and end is not None:
            raise ValueError("schedule(mode=continuous) must not use both end and duration")
        if duration is not None:
            boundary = self.plan_quantity(duration)
            if not self.is_time_point(boundary):
                raise ValueError("schedule(mode=continuous) duration must be a time quantity")
            self.validate_boundary_within_env(
                boundary,
                env_time_boundary,
                message="continuous schedule window exceeds enclosing boundary",
            )
            return self.quantity_payload(boundary)

        assert end is not None
        end_point = self.plan_quantity(end)
        if not self.is_time_point(end_point):
            raise ValueError("schedule(mode=continuous) end must be a time quantity")
        start_seconds = self.time_quantity_to_seconds(start)
        end_seconds = self.time_quantity_to_seconds(end_point)
        if end_seconds < start_seconds - 1e-9:
            raise ValueError("schedule(mode=continuous) end must be >= start")
        boundary = {
            "value": self.seconds_to_unit(end_seconds - start_seconds, start.get("unit")),
            "unit": start.get("unit"),
            "span": start.get("span"),
        }
        self.validate_boundary_within_env(
            boundary,
            env_time_boundary,
            message="continuous schedule window exceeds enclosing boundary",
        )
        return self.quantity_payload(boundary)

    def is_repeat_count_schedule(self, args: Mapping[str, Any]) -> bool:
        marker = args.get("__repeat_count")
        return isinstance(marker, Mapping) and marker.get("kind") == "IRBoolean" and marker.get("value") is True

    def plan_quantity(self, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping) and value.get("kind") == "IRQuantity":
            numeric = value.get("value")
            if not isinstance(numeric, (int, float)):
                raise ValueError("schedule point value must be numeric")
            return {"value": float(numeric), "unit": value.get("unit"), "span": value.get("span")}
        numeric = self.try_eval_numeric_expr(value)
        if numeric is None:
            raise ValueError("schedule points must be statically resolvable quantities")
        return {"value": float(numeric), "unit": None, "span": None}

    def validate_schedule_point_list(self, points: list[dict[str, Any]]) -> None:
        first = points[0]
        if self.is_time_point(first):
            if not all(self.is_time_point(point) for point in points):
                raise ValueError("schedule(at=[...]) points must use consistent types")
            return
        if self.is_unitless_int_point(first):
            if not all(self.is_unitless_int_point(point) for point in points):
                raise ValueError("schedule(at=[...]) points must use consistent types")
            return
        raise ValueError("schedule(at=[...]) supports only time quantities or unitless integer points")

    def validate_points_within_boundary(self, points: list[dict[str, Any]], env_time_boundary: Any) -> None:
        if env_time_boundary is None or not points or not self.is_time_point(points[0]):
            return
        boundary = self.plan_quantity(env_time_boundary)
        if not self.is_time_point(boundary):
            return
        boundary_seconds = self.time_quantity_to_seconds(boundary)
        max_seconds = max(self.time_quantity_to_seconds(point) for point in points)
        if max_seconds > boundary_seconds + 1e-9:
            raise ValueError("env-bound time schedule exceeds enclosing env boundary")

    def validate_boundary_within_env(self, boundary: dict[str, Any], env_time_boundary: Any, *, message: str) -> None:
        if env_time_boundary is None:
            return
        outer = self.plan_quantity(env_time_boundary)
        if not self.is_time_point(boundary) or not self.is_time_point(outer):
            return
        if self.time_quantity_to_seconds(boundary) > self.time_quantity_to_seconds(outer) + 1e-9:
            raise ValueError(message)

    def is_time_point(self, point: Mapping[str, Any]) -> bool:
        return point.get("unit") in TIME_UNIT_SCALE

    def is_unitless_int_point(self, point: Mapping[str, Any]) -> bool:
        return point.get("unit") is None and float(point.get("value", 0.0)).is_integer()

    def expand_time_schedule_points(
        self,
        start: dict[str, Any],
        end: dict[str, Any],
        step: dict[str, Any],
        env_time_boundary: Any = None,
    ) -> list[dict[str, Any]]:
        start_seconds = self.time_quantity_to_seconds(start)
        end_seconds = self.time_quantity_to_seconds(end)
        step_seconds = self.time_quantity_to_seconds(step)
        if step_seconds <= 0:
            raise ValueError("schedule time step must be > 0")
        if env_time_boundary is not None:
            boundary = self.plan_quantity(env_time_boundary)
            if self.is_time_point(boundary) and end_seconds > self.time_quantity_to_seconds(boundary) + 1e-9:
                raise ValueError("env-bound time schedule exceeds enclosing env boundary")
        if start_seconds > end_seconds + 1e-9:
            return []
        unit = start.get("unit")
        points: list[dict[str, Any]] = []
        current = start_seconds
        while current <= end_seconds + 1e-9:
            points.append({"value": self.seconds_to_unit(current, unit), "unit": unit, "span": start.get("span")})
            current += step_seconds
        return points

    def expand_count_schedule_points(
        self,
        start: dict[str, Any],
        end: dict[str, Any],
        step: dict[str, Any],
    ) -> list[dict[str, Any]]:
        start_value = int(start["value"])
        end_value = int(end["value"])
        step_value = int(step["value"])
        if step_value <= 0:
            raise ValueError("schedule count step must be > 0")
        if start_value > end_value:
            return []
        return [{"value": float(v), "unit": None, "span": start.get("span")} for v in range(start_value, end_value + 1, step_value)]

    def time_quantity_to_seconds(self, quantity: Mapping[str, Any]) -> float:
        unit = quantity.get("unit")
        if unit not in TIME_UNIT_SCALE:
            raise ValueError("schedule time points must use supported time units")
        return float(quantity["value"]) * TIME_UNIT_SCALE[unit]

    def seconds_to_unit(self, seconds: float, unit: Any) -> float:
        if unit not in TIME_UNIT_SCALE:
            return seconds
        return seconds / TIME_UNIT_SCALE[unit]

    def quantity_payload(self, quantity: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "kind": "IRQuantity",
            "value": quantity["value"],
            "unit": quantity.get("unit"),
            "span": quantity.get("span"),
        }

    def env_time_boundary_from_payload(self, env_payload: dict[str, Any]) -> Any:
        duration = env_payload.get("duration")
        if self.is_time_quantity_payload(duration):
            return duration
        thermal = env_payload.get("thermal")
        if not isinstance(thermal, dict) or thermal.get("kind") != "IRCall" or thermal.get("name") != "thermal_program":
            return None
        args = thermal.get("args")
        if not isinstance(args, list):
            return None
        for arg in args:
            if isinstance(arg, dict) and arg.get("name") == "duration" and self.is_time_quantity_payload(arg.get("value")):
                return arg.get("value")
        return None

    def is_time_quantity_payload(self, value: Any) -> bool:
        return isinstance(value, dict) and value.get("kind") == "IRQuantity" and value.get("unit") in TIME_UNIT_SCALE
