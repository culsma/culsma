"""Source adapters for action applicability and environment conflicts."""
from typing import Any
from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRStatement, IRMutation, IRWithEnv, IRStep, IRLet, IRCall, IRQuantity
from culsma.pipeline.validate.resolution import ExprResolver
from .rules import ConstraintRules
from .checks import ConstraintContext


class ConstraintSourceValidator:
    """Translate source IR into shared rule inputs and diagnostics."""

    @staticmethod
    def _find_arg_by_name(args, name):
        return next((arg for arg in args if arg.name == name), None)

    @staticmethod
    def classify_constraint_action_family(stmt: IRStatement) -> str | None:
        if isinstance(stmt, IRMutation):
            return "mutation"
        if isinstance(stmt, IRWithEnv) and stmt.explicit_hold and not stmt.statements:
            return "env_hold"
        if isinstance(stmt, IRStep):
            if stmt.name in {"sep", "frac", "img", "ecp", "phy", "agit"}:
                return stmt.name
            return None
        if isinstance(stmt, IRLet) and isinstance(stmt.value, IRCall):
            if stmt.value.name in {"sep", "frac", "img", "ecp", "phy", "stream"}:
                return stmt.value.name
        return None

    @staticmethod
    def validate_active_constraint_compatibility(
        stmt: IRStatement,
        *,
        active_requirements: tuple[str, ...],
    ) -> list[Diagnostic]:
        family = ConstraintSourceValidator.classify_constraint_action_family(stmt)
        return [Diagnostic(code="SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH", message=v.message,
                           span=stmt.span, node_id=getattr(stmt, "id", None))
                for v in ConstraintRules.applicability_violations(family, active_requirements) if v.kind == "family"]

    @staticmethod
    def validate_active_env_constraint_compatibility(
        stmt: IRWithEnv,
        *,
        expr_bindings: dict[str, Any],
        active_requirements: tuple[str, ...],
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        thermal_arg = ConstraintSourceValidator._find_arg_by_name(stmt.env_args, "thermal")
        if thermal_arg is None:
            return diagnostics
        thermal_value = ExprResolver.resolve_bound_expr(thermal_arg.value, expr_bindings)
        if not isinstance(thermal_value, IRQuantity):
            return diagnostics
        for violation in ConstraintRules.context_violations(
            active_requirements,
            [ConstraintContext(thermal=(thermal_value.value, thermal_value.unit))],
        ):
            if violation.kind == "environment":
                diagnostics.append(Diagnostic(code="SEM_CONSTRAINT_ENV_CONFLICT", message=violation.message,
                                              span=thermal_arg.span or stmt.span, node_id=stmt.id))
        return diagnostics
