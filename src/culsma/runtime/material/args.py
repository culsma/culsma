"""Material operation argument reading."""

from __future__ import annotations

from typing import Any


class MaterialArgReader:
    @staticmethod
    def arg_string(value: Any) -> str | None:
        return arg_string(value)

    @staticmethod
    def arg_numeric(value: Any) -> float | None:
        return arg_numeric(value)

    @staticmethod
    def arg_bool(value: Any) -> bool | None:
        return arg_bool(value)

    @staticmethod
    def arg_quantity(value: Any) -> dict[str, Any] | None:
        return arg_quantity(value)

    @staticmethod
    def arg_call(value: Any) -> dict[str, Any] | None:
        return arg_call(value)

    @staticmethod
    def call_arg_value(call: dict[str, Any], name: str) -> Any:
        return call_arg_value(call, name)

    @staticmethod
    def call_arg_string(call: dict[str, Any], name: str) -> str | None:
        return call_arg_string(call, name)

    @staticmethod
    def call_arg_int(call: dict[str, Any], name: str) -> int | None:
        return call_arg_int(call, name)


def arg_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("kind") == "IRString":
            inner = value.get("value")
            return inner if isinstance(inner, str) else None
        if value.get("kind") == "IRIdentifier":
            inner = value.get("name")
            return inner if isinstance(inner, str) else None
    return None


def arg_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        inner = value.get("value")
        if isinstance(inner, (int, float)):
            return float(inner)
    return None


def arg_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRBoolean":
        inner = value.get("value")
        return inner if isinstance(inner, bool) else None
    return None


def arg_quantity(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        v = value.get("value")
        u = value.get("unit")
        if isinstance(v, (int, float)) and isinstance(u, str):
            return {"value": float(v), "unit": u}
    return None


def arg_call(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRCall":
        return value
    return None


def call_arg_value(call: dict[str, Any], name: str) -> Any:
    args = call.get("args")
    if not isinstance(args, list):
        return None
    for arg in args:
        if isinstance(arg, dict) and arg.get("kind") == "IRArg" and arg.get("name") == name:
            return arg.get("value")
    return None


def call_arg_string(call: dict[str, Any], name: str) -> str | None:
    return arg_string(call_arg_value(call, name))


def call_arg_int(call: dict[str, Any], name: str) -> int | None:
    value = call_arg_value(call, name)
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        raw = value.get("value")
        unit = value.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return int(raw)
    return None
