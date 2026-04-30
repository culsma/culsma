"""Expression and environment serialization helpers for plan lowering."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from culsma.pipeline.ir_nodes import (
    IRArg,
    IRAssign,
    IRCall,
    IRConditional,
    IRIdentifier,
    IRRepeat,
    IRString,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.plan_nodes import PlanStep


class PlanExpressionSerializer:
    def contains_unresolved_identifier(self, value: Any) -> bool:
        if isinstance(value, dict):
            kind = value.get("kind")
            if kind == "IRIdentifier":
                return True
            return any(self.contains_unresolved_identifier(v) for v in value.values())
        if isinstance(value, list):
            return any(self.contains_unresolved_identifier(v) for v in value)
        return False

    def linearize_steps(self, steps: list[PlanStep]) -> list[PlanStep]:
        linearized: list[PlanStep] = []
        previous_step_id: str | None = None
        for step in steps:
            deps = [previous_step_id] if previous_step_id is not None else []
            linearized.append(
                PlanStep(
                    step_id=step.step_id,
                    op=step.op,
                    args=step.args,
                    deps=deps,
                    gate=step.gate,
                    span=step.span,
                )
            )
            previous_step_id = step.step_id
        return linearized

    def serialize_arg_list(self, args: list[IRArg], env: dict[str, Any]) -> dict[str, Any]:
        return {arg.name: self.serialize_expr(arg.value, env) for arg in args}

    def invalidate_local_env_names(self, env: dict[str, Any], statements: list[Any]) -> None:
        for name in self.assigned_local_names_ir(statements):
            env[name] = {"kind": "IRIdentifier", "name": name}

    def assigned_local_names_ir(self, statements: list[Any]) -> set[str]:
        names: set[str] = set()
        for stmt in statements:
            if isinstance(stmt, IRAssign):
                if isinstance(stmt.target, IRIdentifier):
                    names.add(stmt.target.name)
            elif isinstance(stmt, IRConditional):
                names.update(self.assigned_local_names_ir(stmt.then_statements))
                names.update(self.assigned_local_names_ir(stmt.else_statements))
            elif isinstance(stmt, IRWithEnv):
                names.update(self.assigned_local_names_ir(stmt.statements))
            elif isinstance(stmt, IRWithConstraint):
                names.update(self.assigned_local_names_ir(stmt.statements))
            elif isinstance(stmt, IRRepeat):
                names.update(self.assigned_local_names_ir(stmt.statements))
        return names

    def find_arg_by_name(self, args: list[IRArg], name: str) -> IRArg | None:
        for arg in args:
            if arg.name == name:
                return arg
        return None

    def load_content_ref_expr(self, call: IRCall, fallback_ref: str) -> Any:
        code_arg = self.find_arg_by_name(call.args, "code")
        if code_arg is not None:
            return code_arg.value
        name_arg = self.find_arg_by_name(call.args, "name")
        if name_arg is not None:
            return name_arg.value
        return IRString(value=fallback_ref, span=call.span)

    def serialize_expr(self, value: Any, env: dict[str, Any] | None = None) -> Any:
        """Serialize IR expression dataclass into JSON-friendly structure."""
        if isinstance(value, IRIdentifier) and env is not None and value.name in env:
            return env[value.name]
        if is_dataclass(value):
            payload = {field.name: getattr(value, field.name) for field in fields(value)}
            if value.__class__.__name__ != "Span":
                payload["kind"] = value.__class__.__name__
            return {k: self.serialize_expr(v, env) for k, v in payload.items()}
        if isinstance(value, list):
            return [self.serialize_expr(v, env) for v in value]
        if isinstance(value, dict):
            return {k: self.serialize_expr(v, env) for k, v in value.items()}
        return value


DEFAULT_PLAN_EXPRESSION_SERIALIZER = PlanExpressionSerializer()
