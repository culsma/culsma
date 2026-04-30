"""Shared mapping normalization from PlanStep to MappingRecord."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.plan_nodes import PlanStep

from .models import MappingRecord


def normalize_step(step: PlanStep) -> MappingRecord:
    gate = step.gate if isinstance(step.gate, dict) else {}
    constraint = gate.get("constraint") if isinstance(gate.get("constraint"), dict) else {}
    raw_requirements = constraint.get("requirements")
    requirements = tuple(item for item in raw_requirements if isinstance(item, str)) if isinstance(raw_requirements, list) else ()
    raw_options = constraint.get("options")
    options = raw_options if isinstance(raw_options, dict) else {}
    env = gate.get("env") if isinstance(gate.get("env"), dict) else None
    env_targets = gate.get("env_targets")

    trace_ref = {"step_id": step.step_id}
    if step.span is not None:
        trace_ref.update(
            {
                "line": getattr(step.span, "line", None),
                "column": getattr(step.span, "column", None),
                "end_line": getattr(step.span, "end_line", None),
                "end_column": getattr(step.span, "end_column", None),
            }
        )

    program_kind, program_args = _extract_program_descriptor(step.args if isinstance(step.args, dict) else {})

    return MappingRecord(
        step_id=step.step_id,
        semantic_op=step.op,
        semantic_args=dict(step.args) if isinstance(step.args, dict) else {},
        program_kind=program_kind,
        program_args=program_args,
        requirements=requirements,
        constraint_options=dict(options),
        env=dict(env) if isinstance(env, dict) else None,
        env_targets=env_targets,
        trace_ref=trace_ref,
    )


def value_to_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(value_to_text(item) for item in value) + "]"
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "IRIdentifier":
            inner = value.get("name")
            return str(inner) if inner is not None else "identifier"
        if kind == "IRString":
            inner = value.get("value")
            return str(inner) if inner is not None else "string"
        if kind == "IRBoolean":
            inner = value.get("value")
            return "true" if inner else "false"
        if kind == "IRQuantity":
            amount = value.get("value")
            unit = value.get("unit")
            return f"{amount}{unit or ''}"
        if kind == "IRPair":
            return f"{value_to_text(value.get('left'))}:{value_to_text(value.get('right'))}"
        if kind == "IRIndex":
            return f"{value_to_text(value.get('base'))}[{value_to_text(value.get('index'))}]"
        if kind == "IRMember":
            return f"{value_to_text(value.get('base'))}.{value.get('member')}"
        if kind == "IRCall":
            name = value.get("name", "call")
            args = value.get("args")
            if isinstance(args, list):
                rendered = ", ".join(_render_call_arg(item) for item in args)
            else:
                rendered = ""
            return f"{name}({rendered})"
        if kind in {"IRList", "IRGroup"}:
            elements = value.get("elements")
            if isinstance(elements, list):
                return "[" + ", ".join(value_to_text(item) for item in elements) + "]"
        return "{" + ", ".join(f"{key}={value_to_text(val)}" for key, val in sorted(value.items())) + "}"
    return str(value)


def _render_call_arg(arg: Any) -> str:
    if not isinstance(arg, dict):
        return value_to_text(arg)
    name = arg.get("name")
    value = arg.get("value")
    if isinstance(name, str):
        return f"{name}={value_to_text(value)}"
    return value_to_text(arg)


def _extract_program_descriptor(args: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    raw_program = args.get("program")
    if not isinstance(raw_program, dict) or raw_program.get("kind") != "IRCall":
        return None, {}
    name = raw_program.get("name")
    if not isinstance(name, str):
        return None, {}
    raw_args = raw_program.get("args")
    if not isinstance(raw_args, list):
        return name, {}
    program_args: dict[str, Any] = {}
    for item in raw_args:
        if not isinstance(item, dict):
            continue
        arg_name = item.get("name")
        if isinstance(arg_name, str):
            program_args[arg_name] = item.get("value")
    return name, program_args
