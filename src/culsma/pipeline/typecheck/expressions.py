"""Expression and quantity services for Canonical IR typecheck."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.common.content_contracts import CONTENT_ENUM_TYPES, parse_content_classification, parse_content_kind
from culsma.common.diagnostics import Diagnostic
from culsma.common.quantity_arithmetic import UNIT_TO_DIMENSION, QuantityArithmeticError, quantity_binary, quantity_parts, quantity_result_unit
from culsma.pipeline.content_inputs import (
    ContentArgumentResolver, ContentArgumentScope, ContentInputSource, ContentResolutionIssue, DeferredContentEnum,
)
from culsma.pipeline.container_views import classify_container_target_view, is_container_target_view
from culsma.pipeline.compat.content_taxonomy import normalize_content_classification
from culsma.pipeline.content_vocab import ContentKind, ContentType, ContainerKind
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRBinary,
    IRBoolean,
    IRCall,
    IRGroup,
    IRIdentifier,
    IRIndex,
    IRList,
    IRMember,
    IRMutation,
    IRPair,
    IRQuantity,
    IRRecord,
    IRSourcePartitionRef,
    IRStep,
    IRString,
    IRUnary,
    IRWithEnv,
)
from culsma.pipeline.program_registry import get_program_spec, is_known_program_kind


_UNIT_TO_DIMENSION = UNIT_TO_DIMENSION


@dataclass(frozen=True)
class DeferredNumeric:
    """Numeric kind retained when control flow prevents static value inference."""

    kind: str
    unit: str | None = None
    span: Any = None


@dataclass(frozen=True)
class InvalidNumeric:
    """A known invalid calculation retained for the consuming slot's diagnostic."""

    kind: str
    error: QuantityArithmeticError


class DeferredQuantity(Exception):
    """A quantity has a known kind/dimension but no statically known value."""

    def __init__(self, numeric: DeferredNumeric | None = None):
        self.numeric = numeric or DeferredNumeric("unknown")


_LEGACY_UNIT_ALIASES: dict[str, str] = {
    "sec": "s",
    "hr": "h",
    "pct": "%",
    "ul": "uL",
    "ml": "mL",
}

_ASSIGNABLE_TYPES = {"bool", "int", "text", "quantity"}
_MATERIAL_SAMPLE_CALLS = {"sep", "frac", "img", "ecp", "phy", "stream"}
_MATERIAL_SAMPLE_STEPS = _MATERIAL_SAMPLE_CALLS | {"agit"}


class TypecheckExpressionServices:
    def typecheck_with_env(self, stmt: IRWithEnv, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for arg in stmt.env_args:
            resolved = self.resolve_bound_expr(arg.value, expr_bindings)
            if arg.name == "thermal":
                if isinstance(resolved, IRCall) and resolved.name == "thermal_program":
                    diagnostics.extend(self.typecheck_thermal_program_call(resolved, node_id=stmt.id, expr_bindings=expr_bindings))
                    continue
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        resolved,
                        expr_bindings=expr_bindings,
                        expected=["temperature"],
                        non_quantity_code="TYPE_ENV_THERMAL_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_ENV_THERMAL_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        label="with env arg 'thermal'",
                        span=arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
            elif arg.name == "duration":
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        resolved,
                        expr_bindings=expr_bindings,
                        expected=["time"],
                        non_quantity_code="TYPE_ENV_DURATION_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_ENV_DURATION_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        label="with env arg 'duration'",
                        span=arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
            elif arg.name in {"co2", "rh"}:
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        resolved,
                        expr_bindings=expr_bindings,
                        expected=["percent"],
                        non_quantity_code="TYPE_ENV_PERCENT_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_ENV_PERCENT_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        label=f"with env arg '{arg.name}'",
                        span=arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
        return diagnostics

    def typecheck_mutation(self, stmt: IRMutation, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(
            self.typecheck_container_target_view_forbidden(
                stmt.target,
                label="mutation target",
                span=stmt.target.span if stmt.target is not None else stmt.span,
                node_id=stmt.id,
                expr_bindings=expr_bindings,
            )
        )
        for source in stmt.sources:
            source_expr = source.left if isinstance(source, IRPair) else source
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    source_expr,
                    node_id=stmt.id,
                    expr_bindings=expr_bindings,
                )
            )
            diagnostics.extend(
                self.typecheck_container_target_view_forbidden(
                    source_expr,
                    label="mutation source",
                    span=source_expr.span or source.span or stmt.span,
                    node_id=stmt.id,
                    expr_bindings=expr_bindings,
                )
            )
            if not isinstance(source, IRPair):
                continue
            amount = self.resolve_bound_expr(source.right, expr_bindings)
            diagnostics.extend(
                self.validate_quantity_dimensions(
                    amount,
                    expr_bindings=expr_bindings,
                    expected=["volume", "mass", "count"],
                    non_quantity_code="TYPE_MUTATION_QUANTITY_UNIT_REQUIRED",
                    mismatch_code="TYPE_MUTATION_QUANTITY_DIMENSION_MISMATCH",
                    unknown_code="TYPE_UNKNOWN_UNIT",
                    missing_unit_code="TYPE_MUTATION_QUANTITY_UNIT_REQUIRED",
                    label="mutation quantified source",
                    span=source.right.span or source.span or stmt.span,
                    node_id=stmt.id,
                )
            )
            amount = self.coerce_quantity_like(amount, expr_bindings)
            if isinstance(amount, IRQuantity) and amount.unit == "cells" and (
                amount.value < 0 or not float(amount.value).is_integer()
            ):
                diagnostics.append(
                    Diagnostic(
                        code="TYPE_CELL_COUNT_VALUE_INVALID",
                        message="mutation cell count must be a non-negative integer",
                        span=source.right.span or source.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
        return diagnostics

    def typecheck_let_call(
        self,
        name: str,
        call: IRCall,
        node_id: str,
        *,
        expr_bindings: dict[str, Any],
        scope: ContentArgumentScope | None = None,
    ) -> list[Diagnostic]:
        scope = scope or ContentArgumentScope(expr_bindings=expr_bindings)
        if call.name == "thermal_program":
            return self.typecheck_thermal_program_call(call, node_id=node_id, expr_bindings=expr_bindings)
        diagnostics = self.typecheck_call_container_target_view_positions(
            call,
            node_id=node_id,
            expr_bindings=expr_bindings,
        )
        if is_known_program_kind(call.name):
            diagnostics.extend(self.typecheck_program_call(call, node_id=node_id, expr_bindings=expr_bindings))
            return diagnostics
        if call.name == "DefineContent":
            diagnostics.extend(self.typecheck_define_content_args(call.args, call.span, node_id, scope=scope))
            return diagnostics
        if call.name != "AllocContainer":
            return diagnostics
        for arg in call.args:
            if arg.name == "kind":
                diagnostics.extend(self.typecheck_content_enum_argument(arg, ContainerKind, node_id, scope))
            if arg.name == "capacity":
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        self.resolve_bound_expr(arg.value, expr_bindings),
                        expr_bindings=expr_bindings,
                        expected=["volume"],
                        non_quantity_code="TYPE_CONTAINER_CAPACITY_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_CONTAINER_CAPACITY_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        missing_unit_code="TYPE_CONTAINER_CAPACITY_DIMENSION_MISMATCH",
                        label=f"constructor capacity for '{name}'",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
            elif arg.name == "load":
                diagnostics.extend(self.typecheck_constructor_load(arg.value, node_id=node_id, expr_bindings=expr_bindings, scope=scope))
        return diagnostics

    def typecheck_call_container_target_view_positions(
        self,
        call: IRCall,
        *,
        node_id: str,
        expr_bindings: dict[str, Any],
    ) -> list[Diagnostic]:
        if call.name not in _MATERIAL_SAMPLE_CALLS:
            return []
        sample_arg = next((arg for arg in call.args if arg.name == "sample"), None)
        if sample_arg is None:
            return []
        return self.typecheck_container_target_view_forbidden(
            sample_arg.value,
            label=f"{call.name}(...) sample",
            span=sample_arg.span or call.span,
            node_id=node_id,
            expr_bindings=expr_bindings,
        )

    def typecheck_step_container_target_view_positions(
        self,
        step: IRStep,
        *,
        expr_bindings: dict[str, Any],
    ) -> list[Diagnostic]:
        if step.name not in _MATERIAL_SAMPLE_STEPS:
            return []
        sample_arg = next((arg for arg in step.args if arg.name == "sample"), None)
        if sample_arg is None:
            return []
        return self.typecheck_container_target_view_forbidden(
            sample_arg.value,
            label=f"{step.name}(...) sample",
            span=sample_arg.span or step.span,
            node_id=step.id,
            expr_bindings=expr_bindings,
        )

    def typecheck_container_target_view_forbidden(
        self,
        expr: Any,
        *,
        label: str,
        span,
        node_id: str | None,
        expr_bindings: dict[str, Any],
    ) -> list[Diagnostic]:
        if expr is None:
            return []
        resolved = self.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, IRSourcePartitionRef):
            return self.typecheck_container_target_view_forbidden(
                resolved.source,
                label=f"{label} source partition source",
                span=resolved.source.span or span,
                node_id=node_id,
                expr_bindings=expr_bindings,
            )
        if not is_container_target_view(resolved):
            return []
        return [
            Diagnostic(
                code="TYPE_CONTAINER_TARGET_VIEW_POSITION_INVALID",
                message=f"{label} expects a material container, not a container target view",
                span=getattr(resolved, "span", None) or span,
                node_id=node_id,
            )
        ]

    def typecheck_thermal_program_call(self, call: IRCall, *, node_id: str, expr_bindings: dict[str, Any] | None = None) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for arg in call.args:
            if arg.name in {"from", "to"}:
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        arg.value,
                        expr_bindings=expr_bindings,
                        expected=["temperature"],
                        non_quantity_code="TYPE_ENV_THERMAL_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_ENV_THERMAL_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        label=f"thermal_program arg '{arg.name}'",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
            elif arg.name == "duration":
                diagnostics.extend(
                    self.validate_quantity_dimensions(
                        arg.value,
                        expr_bindings=expr_bindings,
                        expected=["time"],
                        non_quantity_code="TYPE_ENV_DURATION_DIMENSION_MISMATCH",
                        mismatch_code="TYPE_ENV_DURATION_DIMENSION_MISMATCH",
                        unknown_code="TYPE_UNKNOWN_UNIT",
                        label="thermal_program arg 'duration'",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
        return diagnostics

    def typecheck_constructor_load(self, value: Any, *, node_id: str, expr_bindings: dict[str, Any], scope: ContentArgumentScope | None = None) -> list[Diagnostic]:
        resolved = self.resolve_bound_expr(value, expr_bindings)
        if not isinstance(resolved, IRList):
            return []
        diagnostics: list[Diagnostic] = []
        for item in resolved.elements:
            if not isinstance(item, IRPair):
                continue
            if isinstance(item.left, IRCall) and item.left.name == "DefineContent":
                diagnostics.extend(self.typecheck_define_content_args(item.left.args, item.left.span, node_id, scope=scope or ContentArgumentScope(expr_bindings=expr_bindings)))
            amount = self.resolve_bound_expr(item.right, expr_bindings)
            diagnostics.extend(
                self.validate_quantity_dimensions(
                    amount,
                    expr_bindings=expr_bindings,
                    expected=["volume", "mass", "count"],
                    non_quantity_code="TYPE_LOAD_QUANTITY_UNIT_REQUIRED",
                    mismatch_code="TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH",
                    unknown_code="TYPE_UNKNOWN_UNIT",
                    missing_unit_code="TYPE_LOAD_QUANTITY_UNIT_REQUIRED",
                    label="constructor load quantity",
                    span=item.right.span or item.span,
                    node_id=node_id,
                )
            )
            amount = self.coerce_quantity_like(amount, expr_bindings)
            if isinstance(amount, IRQuantity) and amount.unit == "cells":
                if amount.value < 0 or not float(amount.value).is_integer():
                    diagnostics.append(
                        Diagnostic(
                            code="TYPE_CELL_COUNT_VALUE_INVALID",
                            message="constructor load cell count must be a non-negative integer",
                            span=item.right.span or item.span,
                            node_id=node_id,
                        )
                    )
                content_scope = scope or ContentArgumentScope(expr_bindings=expr_bindings)
                content_results = {
                    arg.name: ContentArgumentResolver.resolve_argument(
                        arg.value, ContentKind if arg.name == "kind" else ContentType, content_scope,
                    )
                    for arg in item.left.args if arg.name in {"kind", "type"}
                } if isinstance(item.left, IRCall) else {}
                content_kind = content_results["kind"].token if "kind" in content_results else None
                content_type = content_results["type"].token if "type" in content_results else None
                classification = parse_content_classification(content_kind, content_type)
                if (classification is None and content_kind is not None and content_type is not None
                        and all(result.source is not ContentInputSource.ENUM for result in content_results.values())):
                    classification = normalize_content_classification(content_kind, content_type).classification
                effective_kind = classification.kind if classification is not None else parse_content_kind(content_kind)
                if content_kind is not None and effective_kind is not ContentKind.BIO_CELLULAR:
                    diagnostics.append(
                        Diagnostic(
                            code="TYPE_LOAD_COUNT_CONTENT_MISMATCH",
                            message="unit 'cells' requires bio_cellular content",
                            span=item.left.span or item.span,
                            node_id=node_id,
                        )
                    )
        return diagnostics

    def validate_quantity_dimensions(
        self,
        value: Any,
        *,
        expected: list[str],
        non_quantity_code: str,
        mismatch_code: str,
        unknown_code: str,
        missing_unit_code: str | None = None,
        label: str,
        span,
        node_id: str | None,
        expr_bindings: dict[str, Any] | None = None,
    ) -> list[Diagnostic]:
        try:
            resolved = self.evaluate_quantity(value, expr_bindings or {})
        except DeferredQuantity as exc:
            resolved = exc.numeric
            if resolved.kind == "unknown" or (resolved.kind == "quantity" and resolved.unit is None):
                return []
        except QuantityArithmeticError as exc:
            code = {
                "zero": "TYPE_QUANTITY_DIVISION_BY_ZERO",
                "unit": unknown_code,
                "nonfinite": "TYPE_QUANTITY_VALUE_NONFINITE",
                "dimension": mismatch_code,
            }.get(exc.reason, non_quantity_code)
            return [Diagnostic(code=code, message=f"{label}: {exc}", span=span, node_id=node_id)]
        if resolved is None:
            return [
                Diagnostic(
                    code=non_quantity_code,
                    message=f"{label} expects quantity with unit in dimensions {expected}",
                    span=span,
                    node_id=node_id,
                )
            ]
        unit = resolved.unit
        if unit is None:
            return [
                Diagnostic(
                    code=missing_unit_code or unknown_code,
                    message=f"Unknown or missing unit for {label}",
                    span=resolved.span or span,
                    node_id=node_id,
                )
            ]

        if unit not in _UNIT_TO_DIMENSION:
            return [
                Diagnostic(
                    code=unknown_code,
                    message=f"Unknown or missing unit for {label}",
                    span=resolved.span or span,
                    node_id=node_id,
                )
            ]

        got_dim = _UNIT_TO_DIMENSION[unit]
        if got_dim not in expected:
            return [
                Diagnostic(
                    code=mismatch_code,
                    message=f"{label} expects {expected}, got unit '{unit}' ({got_dim})",
                    span=resolved.span or span,
                    node_id=node_id,
                )
            ]
        if unit in _LEGACY_UNIT_ALIASES:
            canonical = _LEGACY_UNIT_ALIASES[unit]
            return [
                Diagnostic(
                    code="TYPE_UNIT_LEGACY_ALIAS",
                    message=(
                        f"Unit '{unit}' is a legacy alias for {label}; "
                        f"use canonical unit '{canonical}' to avoid this warning."
                    ),
                    span=resolved.span or span,
                    severity="warning",
                    node_id=node_id,
                )
            ]
        return []

    def evaluate_quantity(self, value: Any, expr_bindings: dict[str, Any], seen: frozenset[str] = frozenset()) -> IRQuantity | None:
        if isinstance(value, InvalidNumeric):
            raise value.error
        if isinstance(value, DeferredNumeric):
            raise DeferredQuantity(value)
        if isinstance(value, IRIdentifier):
            if value.name not in expr_bindings or value.name in seen:
                raise DeferredQuantity()
            return self.evaluate_quantity(expr_bindings[value.name], expr_bindings, seen | {value.name})
        if isinstance(value, IRQuantity):
            quantity_parts((value.value, value.unit) if value.unit is not None else value.value)
            return value
        if isinstance(value, IRUnary) and value.op == "-":
            inner = self.evaluate_quantity(value.operand, expr_bindings, seen)
            if inner is None:
                return None
            return IRQuantity(value=-inner.value, unit=inner.unit, span=value.span or inner.span)
        if isinstance(value, IRBinary) and value.op in {"+", "-", "*", "/"}:
            operands = []
            for operand in (value.left, value.right):
                try:
                    operands.append(self.evaluate_quantity(operand, expr_bindings, seen))
                except DeferredQuantity as exc:
                    operands.append(exc.numeric)
            left, right = operands
            if left is None or right is None:
                return None
            if value.op == "/" and isinstance(right, IRQuantity) and right.value == 0:
                raise QuantityArithmeticError("zero", "Division by zero in quantity expression")
            deferred = [operand for operand in operands if isinstance(operand, DeferredNumeric)]
            if deferred:
                if any(operand.kind == "unknown" or (operand.kind == "quantity" and operand.unit is None)
                       for operand in deferred):
                    raise DeferredQuantity()
                unit = quantity_result_unit(value.op, left.unit, right.unit)
                raise DeferredQuantity(DeferredNumeric("quantity" if unit is not None else "int", unit))
            result = quantity_binary(
                value.op,
                (left.value, left.unit) if left.unit is not None else left.value,
                (right.value, right.unit) if right.unit is not None else right.value,
            )
            number, unit = result if isinstance(result, tuple) else (result, None)
            return IRQuantity(value=number, unit=unit, span=value.span)
        return None

    def numeric_binding(self, value: Any, expr_bindings: dict[str, Any]) -> IRQuantity | DeferredNumeric | InvalidNumeric | None:
        """Capture known values, defer unknown values, and preserve known errors."""
        try:
            return self.evaluate_quantity(value, expr_bindings)
        except DeferredQuantity as exc:
            return exc.numeric if exc.numeric.kind in {"int", "quantity"} else None
        except QuantityArithmeticError as exc:
            kind = self.classify_local_expr_type(value, expr_bindings=expr_bindings)
            return InvalidNumeric(kind, exc)

    def parameter_default_binding(self, value: Any) -> Any:
        """Retain the default's numeric dimension, without assuming its value at every call."""
        quantity = self.coerce_quantity_like(value)
        if quantity is None:
            return value
        return DeferredNumeric("quantity" if quantity.unit is not None else "int", quantity.unit)

    def coerce_quantity_like(self, value: Any, expr_bindings: dict[str, Any] | None = None) -> IRQuantity | None:
        try:
            return self.evaluate_quantity(value, expr_bindings or {})
        except (DeferredQuantity, QuantityArithmeticError):
            return None

    def resolve_bound_expr(self, expr: Any, expr_bindings: dict[str, Any]) -> Any:
        seen: set[str] = set()
        current = expr
        while isinstance(current, IRIdentifier) and current.name in expr_bindings and current.name not in seen:
            seen.add(current.name)
            current = expr_bindings[current.name]
        return current

    def typecheck_assignment(self, stmt: IRAssign, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
        if isinstance(stmt.target, IRMember):
            return self.typecheck_member_assignment(stmt, expr_bindings=expr_bindings)
        diagnostics: list[Diagnostic] = []
        if not isinstance(stmt.target, IRIdentifier):
            return [
                Diagnostic(
                    code="TYPE_LOCAL_ASSIGN_TARGET_FORBIDDEN",
                    message="Assignment target is not a supported assignable local scalar",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            ]
        target_expr = expr_bindings.get(stmt.target.name)
        target_type = self.classify_local_expr_type(target_expr, expr_bindings=expr_bindings)
        value_type = self.classify_local_expr_type(stmt.value, expr_bindings=expr_bindings)

        if target_type not in _ASSIGNABLE_TYPES and target_type not in CONTENT_ENUM_TYPES:
            diagnostics.append(
                Diagnostic(
                    code="TYPE_LOCAL_ASSIGN_TARGET_FORBIDDEN",
                    message=f"Assignment target '{stmt.target.name}' is not a supported assignable local scalar",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
            return diagnostics

        if value_type != target_type:
            diagnostics.append(
                Diagnostic(
                    code="TYPE_LOCAL_ASSIGN_MISMATCH",
                    message=f"Assignment to '{stmt.target.name}' expects {target_type}, got {value_type}",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
        return diagnostics

    def typecheck_member_assignment(self, stmt: IRAssign, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        path = self.member_assignment_path(stmt.target)
        if path is None:
            return [
                Diagnostic(
                    code="TYPE_MEMBER_ASSIGN_TARGET_FORBIDDEN",
                    message="Member assignment target must be a member path rooted at a local name",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            ]
        root_name, members = path
        root_expr = expr_bindings.get(root_name)
        root_type = self.classify_local_expr_type(root_expr, expr_bindings=expr_bindings)
        if root_type not in {"data_ref", "data_group_ref"}:
            diagnostics.append(
                Diagnostic(
                    code="TYPE_MEMBER_ASSIGN_TARGET_FORBIDDEN",
                    message=f"Member assignment root '{root_name}' must be data_ref or data_group_ref, got {root_type}",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
            return diagnostics
        if len(members) < 2 or members[0] != "result":
            diagnostics.append(
                Diagnostic(
                    code="TYPE_MEMBER_ASSIGN_PATH_FORBIDDEN",
                    message="Member assignment only supports data_ref/data_group_ref result fields via <data>.result.<field...>",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
        return diagnostics

    def member_assignment_path(self, expr: Any) -> tuple[str, list[str]] | None:
        members: list[str] = []
        current = expr
        while isinstance(current, IRMember):
            members.append(current.member)
            current = current.base
        if not isinstance(current, IRIdentifier):
            return None
        members.reverse()
        return current.name, members

    def classify_local_expr_type(self, expr: Any, *, expr_bindings: dict[str, Any]) -> str:
        deferred = expr_bindings.get(expr.name) if isinstance(expr, IRIdentifier) else expr
        if isinstance(deferred, DeferredContentEnum):
            return deferred.enum_type.__name__
        enum_result = ContentArgumentResolver.resolve_argument(expr, None, ContentArgumentScope(expr_bindings=expr_bindings))
        if enum_result.source is ContentInputSource.ENUM and enum_result.token is not None:
            return type(enum_result.value).__name__
        resolved = self.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, (DeferredNumeric, InvalidNumeric)):
            return resolved.kind
        if isinstance(resolved, IRBoolean):
            return "bool"
        if isinstance(resolved, IRString):
            return "text"
        if isinstance(resolved, IRQuantity):
            return "quantity" if resolved.unit is not None else "int"
        if isinstance(resolved, (IRGroup, IRIndex)):
            return "group_ref"
        if isinstance(resolved, IRSourcePartitionRef):
            return "source_portion_ref"
        if isinstance(resolved, IRMember):
            view = classify_container_target_view(resolved)
            if view is not None:
                return "container_contents_view" if view.kind == "contents" else "container_structure_facet"
            base_type = self.classify_local_expr_type(resolved.base, expr_bindings=expr_bindings)
            if base_type in {"data_ref", "data_group_ref", "data_schema_ref", "unit_stream_ref", "marker_panel_ref"}:
                return "unknown"
            return "unknown"
        if isinstance(resolved, IRCall):
            if resolved.name == "AllocContainer":
                return "container_ref"
            if resolved.name in {"group", "plate"}:
                return "group_ref"
            if resolved.name == "schedule":
                return "schedule"
            if resolved.name == "stream":
                return "unit_stream_ref"
            if resolved.name == "markers":
                return "marker_panel_ref"
            if resolved.name == "data_schema":
                return "data_schema_ref"
            if resolved.name == "data_ref":
                return "data_ref"
            if resolved.name == "data_group_ref":
                return "data_group_ref"
            if is_known_program_kind(resolved.name) or resolved.name.endswith("_program"):
                return "program"
            if resolved.name in {"img", "ecp", "phy"}:
                sample_arg = next((arg for arg in resolved.args if arg.name == "sample"), None)
                if sample_arg is not None and self.classify_local_expr_type(sample_arg.value, expr_bindings=expr_bindings) == "group_ref":
                    return "data_group_ref"
                return "data_ref"
            if resolved.name in {"sep", "frac"}:
                return "group_ref"
        if isinstance(resolved, IRIdentifier):
            return "unknown"
        if isinstance(resolved, IRUnary):
            inner = self.classify_local_expr_type(resolved.operand, expr_bindings=expr_bindings)
            return inner if inner in {"int", "quantity"} else "unknown"
        if isinstance(resolved, IRBinary):
            left = self.classify_local_expr_type(resolved.left, expr_bindings=expr_bindings)
            right = self.classify_local_expr_type(resolved.right, expr_bindings=expr_bindings)
            if resolved.op in {"and", "or", "==", "!=", "<", ">", "<=", ">="}:
                return "bool"
            if left == right == "int" and resolved.op in {"+", "-", "*", "/"}:
                return "int"
            if left == right == "quantity":
                if resolved.op in {"+", "-"}:
                    return "quantity"
                if resolved.op == "/":
                    return "int"
            if resolved.op == "*" and {left, right} == {"int", "quantity"}:
                return "quantity"
            if resolved.op == "/" and left == "quantity" and right == "int":
                return "quantity"
        return "unknown"

    def typecheck_content_enum_argument(self, arg, expected_enum, node_id, scope: ContentArgumentScope) -> list[Diagnostic]:
        result = ContentArgumentResolver.resolve_argument(arg.value, expected_enum, scope)
        if result.issue is ContentResolutionIssue.WRONG_ENUM_TYPE:
            return [Diagnostic(
                code="TYPE_CONTENT_ENUM_TYPE_MISMATCH",
                message=f"Argument '{arg.name}' expects {expected_enum.__name__}, got {result.detail}",
                span=arg.value.span if hasattr(arg.value, "span") else arg.span,
                node_id=node_id,
            )]
        if result.issue is not ContentResolutionIssue.NON_TEXT:
            return []
        code = "TYPE_CONTAINER_KIND_NOT_TEXT" if expected_enum is ContainerKind else f"TYPE_CONTENT_{arg.name.upper()}_NOT_TEXT"
        return [Diagnostic(
            code=code, message=f"Argument '{arg.name}' must be {expected_enum.__name__} or a compatible text input",
            span=arg.span, node_id=node_id,
        )]

    def typecheck_content_descriptors(self, step: IRStep, *, scope: ContentArgumentScope | None = None) -> list[Diagnostic]:
        scope = scope or ContentArgumentScope()
        if step.name == "AllocContainer":
            return [d for arg in step.args if arg.name == "kind"
                    for d in self.typecheck_content_enum_argument(arg, ContainerKind, step.id, scope)]
        if step.name != "DefineContent":
            return []
        return self.typecheck_define_content_args(step.args, step.span, step.id, scope=scope)

    def typecheck_define_content_args(self, args: list[Any], span, node_id: str, *, scope: ContentArgumentScope | None = None) -> list[Diagnostic]:
        scope = scope or ContentArgumentScope()
        diagnostics: list[Diagnostic] = []
        for arg in args:
            if arg.name in {"kind", "type"}:
                expected_enum = ContentKind if arg.name == "kind" else ContentType
                diagnostics.extend(self.typecheck_content_enum_argument(arg, expected_enum, node_id, scope))
            elif arg.name == "code" and not isinstance(arg.value, (IRString, IRIdentifier)):
                diagnostics.append(Diagnostic(
                    code="TYPE_CONTENT_CODE_NOT_TEXT", message="DefineContent arg 'code' must be text-like",
                    span=arg.span or span, node_id=node_id,
                ))
            elif arg.name == "attrs" and not isinstance(arg.value, IRRecord):
                diagnostics.append(Diagnostic(
                    code="TYPE_CONTENT_ATTRS_NOT_RECORD", message="DefineContent arg 'attrs' must be record-like",
                    span=arg.span or span, node_id=node_id,
                ))
        return diagnostics

    def typecheck_program_calls_in_expr(
        self,
        expr: Any,
        *,
        node_id: str,
        expr_bindings: dict[str, Any],
        seen_names: set[str] | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        seen = set() if seen_names is None else set(seen_names)
        if isinstance(expr, IRIdentifier):
            if expr.name in seen:
                return diagnostics
            seen.add(expr.name)
        resolved = self.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, IRCall):
            if is_known_program_kind(resolved.name):
                diagnostics.extend(self.typecheck_program_call(resolved, node_id=node_id, expr_bindings=expr_bindings))
            for arg in resolved.args:
                diagnostics.extend(
                    self.typecheck_program_calls_in_expr(
                        arg.value,
                        node_id=node_id,
                        expr_bindings=expr_bindings,
                        seen_names=seen,
                    )
                )
            return diagnostics
        if isinstance(resolved, IRList):
            for item in resolved.elements:
                diagnostics.extend(
                    self.typecheck_program_calls_in_expr(
                        item,
                        node_id=node_id,
                        expr_bindings=expr_bindings,
                        seen_names=seen,
                    )
                )
            return diagnostics
        if isinstance(resolved, IRRecord):
            for value in resolved.entries.values():
                diagnostics.extend(
                    self.typecheck_program_calls_in_expr(
                        value,
                        node_id=node_id,
                        expr_bindings=expr_bindings,
                        seen_names=seen,
                    )
                )
            return diagnostics
        if isinstance(resolved, IRGroup):
            for item in resolved.elements:
                diagnostics.extend(
                    self.typecheck_program_calls_in_expr(
                        item,
                        node_id=node_id,
                        expr_bindings=expr_bindings,
                        seen_names=seen,
                    )
                )
            return diagnostics
        if isinstance(resolved, IRPair):
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.left,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.right,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            return diagnostics
        if isinstance(resolved, IRSourcePartitionRef):
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.source,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.program,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.index,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            return diagnostics
        if isinstance(resolved, IRBinary):
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.left,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.right,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            return diagnostics
        if isinstance(resolved, IRUnary):
            return self.typecheck_program_calls_in_expr(
                resolved.operand,
                node_id=node_id,
                expr_bindings=expr_bindings,
                seen_names=seen,
            )
        if isinstance(resolved, IRMember):
            return self.typecheck_program_calls_in_expr(
                resolved.base,
                node_id=node_id,
                expr_bindings=expr_bindings,
                seen_names=seen,
            )
        if isinstance(resolved, IRIndex):
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.base,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
            diagnostics.extend(
                self.typecheck_program_calls_in_expr(
                    resolved.index,
                    node_id=node_id,
                    expr_bindings=expr_bindings,
                    seen_names=seen,
                )
            )
        return diagnostics

    def typecheck_program_call(self, call: IRCall, *, node_id: str, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        spec = get_program_spec(call.name)
        if spec is None:
            return diagnostics

        field_specs = {field.name: field for field in spec.fields}
        for arg in call.args:
            field_spec = field_specs.get(arg.name)
            if field_spec is None:
                continue
            resolved = self.resolve_bound_expr(arg.value, expr_bindings)
            if field_spec.value_kind == "quantity":
                diagnostics.extend(
                    self.validate_program_quantity_field(
                        resolved,
                        expr_bindings=expr_bindings,
                        field_name=arg.name,
                        program_name=call.name,
                        dimension=field_spec.dimension,
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
                continue
            if field_spec.value_kind == "bool" and not isinstance(resolved, IRBoolean):
                diagnostics.append(
                    Diagnostic(
                        code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
                        message=f"Program arg '{arg.name}' in '{call.name}' expects a boolean value",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
                continue
            if field_spec.value_kind == "int":
                if isinstance(resolved, DeferredNumeric) and resolved.kind == "int":
                    continue
                if not isinstance(resolved, IRQuantity) or resolved.unit is not None or int(resolved.value) != resolved.value:
                    diagnostics.append(
                        Diagnostic(
                            code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
                            message=f"Program arg '{arg.name}' in '{call.name}' expects an integer literal",
                            span=arg.span or call.span,
                            node_id=node_id,
                        )
                    )
                continue
            if field_spec.value_kind == "list" and not isinstance(resolved, IRList):
                diagnostics.append(
                    Diagnostic(
                        code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
                        message=f"Program arg '{arg.name}' in '{call.name}' expects a list value",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
                continue
            if field_spec.value_kind in {"text", "text_enum"} and not isinstance(resolved, (IRString, IRIdentifier)):
                diagnostics.append(
                    Diagnostic(
                        code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
                        message=f"Program arg '{arg.name}' in '{call.name}' expects a text-like value",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
        return diagnostics

    def validate_program_quantity_field(
        self,
        value: Any,
        *,
        field_name: str,
        program_name: str,
        dimension: str | None,
        span,
        node_id: str,
        expr_bindings: dict[str, Any] | None = None,
    ) -> list[Diagnostic]:
        if dimension == "centrifuge_speed":
            return self.validate_centrifuge_speed_quantity(
                value,
                field_name=field_name,
                program_name=program_name,
                span=span,
                node_id=node_id,
            )
        if dimension is None:
            return []
        return self.validate_quantity_dimensions(
            value,
            expr_bindings=expr_bindings,
            expected=[dimension],
            non_quantity_code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
            mismatch_code="TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH",
            unknown_code="TYPE_UNKNOWN_UNIT",
            missing_unit_code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
            label=f"Program arg '{field_name}' in '{program_name}'",
            span=span,
            node_id=node_id,
        )

    def validate_centrifuge_speed_quantity(self, value: Any, *, field_name: str, program_name: str, span, node_id: str) -> list[Diagnostic]:
        if not isinstance(value, IRQuantity) and not (isinstance(value, DeferredNumeric) and value.kind == "quantity"):
            return [
                Diagnostic(
                    code="TYPE_PROGRAM_FIELD_KIND_MISMATCH",
                    message=f"Program arg '{field_name}' in '{program_name}' expects a centrifuge speed quantity",
                    span=span,
                    node_id=node_id,
                )
            ]
        if value.unit not in {"g", "rpm"}:
            return [
                Diagnostic(
                    code="TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH",
                    message=f"Program arg '{field_name}' in '{program_name}' expects unit 'g' or 'rpm'",
                    span=span,
                    node_id=node_id,
                )
            ]
        return []


DEFAULT_TYPECHECK_EXPRESSION_SERVICES = TypecheckExpressionServices()


def _typecheck_with_env(stmt: IRWithEnv, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_with_env(stmt, expr_bindings=expr_bindings)


def _typecheck_mutation(stmt: IRMutation, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_mutation(stmt, expr_bindings=expr_bindings)


def _typecheck_let_call(name: str, call: IRCall, node_id: str, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_let_call(name, call, node_id, expr_bindings=expr_bindings)


def _typecheck_thermal_program_call(call: IRCall, *, node_id: str) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_thermal_program_call(call, node_id=node_id)


def _typecheck_constructor_load(value: Any, *, node_id: str, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_constructor_load(value, node_id=node_id, expr_bindings=expr_bindings)


def _validate_quantity_dimensions(
    value: Any,
    *,
    expected: list[str],
    non_quantity_code: str,
    mismatch_code: str,
    unknown_code: str,
    missing_unit_code: str | None = None,
    label: str,
    span,
    node_id: str | None,
) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.validate_quantity_dimensions(
        value,
        expected=expected,
        non_quantity_code=non_quantity_code,
        mismatch_code=mismatch_code,
        unknown_code=unknown_code,
        missing_unit_code=missing_unit_code,
        label=label,
        span=span,
        node_id=node_id,
    )


def _content_call_kind_type(call: IRCall) -> tuple[str | None, str | None]:
    values: dict[str, str] = {}
    for arg in call.args:
        if arg.name not in {"kind", "type"}:
            continue
        if isinstance(arg.value, IRString):
            values[arg.name] = arg.value.value
        elif isinstance(arg.value, IRIdentifier):
            values[arg.name] = arg.value.name
    return values.get("kind"), values.get("type")


def _coerce_quantity_like(value: Any) -> IRQuantity | None:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.coerce_quantity_like(value)


def _resolve_bound_expr(expr: Any, expr_bindings: dict[str, Any]) -> Any:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.resolve_bound_expr(expr, expr_bindings)


def _typecheck_assignment(stmt: IRAssign, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_assignment(stmt, expr_bindings=expr_bindings)


def _typecheck_member_assignment(stmt: IRAssign, *, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_member_assignment(stmt, expr_bindings=expr_bindings)


def _member_assignment_path(expr: Any) -> tuple[str, list[str]] | None:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.member_assignment_path(expr)


def _classify_local_expr_type(expr: Any, *, expr_bindings: dict[str, Any]) -> str:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.classify_local_expr_type(expr, expr_bindings=expr_bindings)


def _typecheck_content_descriptors(step: IRStep) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_content_descriptors(step)


def _typecheck_define_content_args(args: list[Any], span, node_id: str) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_define_content_args(args, span, node_id)


def _typecheck_program_calls_in_expr(
    expr: Any,
    *,
    node_id: str,
    expr_bindings: dict[str, Any],
    seen_names: set[str] | None = None,
) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_program_calls_in_expr(
        expr,
        node_id=node_id,
        expr_bindings=expr_bindings,
        seen_names=seen_names,
    )


def _typecheck_program_call(call: IRCall, *, node_id: str, expr_bindings: dict[str, Any]) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.typecheck_program_call(call, node_id=node_id, expr_bindings=expr_bindings)


def _validate_program_quantity_field(
    value: Any,
    *,
    field_name: str,
    program_name: str,
    dimension: str | None,
    span,
    node_id: str,
) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.validate_program_quantity_field(
        value,
        field_name=field_name,
        program_name=program_name,
        dimension=dimension,
        span=span,
        node_id=node_id,
    )


def _validate_centrifuge_speed_quantity(value: Any, *, field_name: str, program_name: str, span, node_id: str) -> list[Diagnostic]:
    return DEFAULT_TYPECHECK_EXPRESSION_SERVICES.validate_centrifuge_speed_quantity(
        value,
        field_name=field_name,
        program_name=program_name,
        span=span,
        node_id=node_id,
    )
