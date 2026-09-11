"""Container and content constructor semantic contracts."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.compat import content_syntax
from culsma.pipeline.compat.content_taxonomy import KNOWN_CONTENT_KINDS
from culsma.common.content_contracts import parse_content_classification
from culsma.pipeline.content_vocab import (
    CONTAINER_KIND_WHITELIST,
    CONTENT_KIND_WHITELIST,
    CONTENT_TYPE_PATTERN,
    ContainerKind,
    ContentKind,
    ContentType,
)
from culsma.pipeline.content_inputs import (
    ContentArgumentResolver, ContentArgumentScope, ContentInputSource, ContentResolutionStatus,
    content_enum_diagnostics,
)
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRList, IRPair, IRStep
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS

from .operations import OperationContractValidator
from .resolution import ExprResolver


class ConstructorValidator:
    @staticmethod
    def validate_container_content_constructor_semantics(
        step: IRStep,
        literal_bindings: dict[str, Any],
        *,
        content_whitelist_mode: str,
        content_type_policy: str,
        scope: ContentArgumentScope | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        scope = scope or ContentArgumentScope(literal_bindings=literal_bindings)
        if step.name == "AllocContainer":
            kind_arg = find_arg(step, "kind")
            kind_result = ContentArgumentResolver.resolve_argument(kind_arg.value if kind_arg else None, ContainerKind, scope)
            kind_value = kind_result.token
            diagnostics.extend(content_enum_diagnostics(kind_result, span=kind_arg.value.span if kind_arg else step.span, node_id=step.id))
            if kind_value is not None and kind_value not in CONTAINER_KIND_WHITELIST:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_CONTAINER_KIND",
                        message=f"Unsupported container kind '{kind_value}'",
                        span=(kind_arg.span if kind_arg is not None else step.span),
                        node_id=step.id,
                    )
                )
            diagnostics.extend(
                ConstructorValidator.validate_surface_capacity_forbidden(
                    kind_value=kind_value,
                    capacity_arg=find_arg(step, "capacity"),
                    span=step.span,
                    node_id=step.id,
                )
            )
            return diagnostics

        if step.name != "DefineContent":
            return diagnostics

        kind_arg = find_arg(step, "kind")
        kind_result = ContentArgumentResolver.resolve_argument(kind_arg.value if kind_arg else None, ContentKind, scope)
        kind_value = kind_result.token
        diagnostics.extend(content_enum_diagnostics(kind_result, span=kind_arg.value.span if kind_arg else step.span, node_id=step.id))
        if kind_arg is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_MISSING_CONTENT_KIND",
                    message="DefineContent requires arg 'kind'",
                    span=step.span,
                    node_id=step.id,
                )
            )
            return diagnostics

        compat_mode = content_whitelist_mode == "compat"
        if kind_value is not None and kind_value not in CONTENT_KIND_WHITELIST and not (
            compat_mode and kind_value in KNOWN_CONTENT_KINDS
        ):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTENT_KIND",
                    message=f"Unsupported content kind '{kind_value}'",
                    span=kind_arg.span or step.span,
                    node_id=step.id,
                )
            )

        type_arg = find_arg(step, "type")
        type_result = ContentArgumentResolver.resolve_argument(type_arg.value if type_arg else None, ContentType, scope)
        type_value = type_result.token
        diagnostics.extend(content_enum_diagnostics(type_result, span=type_arg.value.span if type_arg else step.span, node_id=step.id))
        if type_arg is not None and type_result.status is not ContentResolutionStatus.RESOLVED:
            return diagnostics
        compat_mode = compat_mode and kind_result.source is not ContentInputSource.ENUM and type_result.source is not ContentInputSource.ENUM
        if type_arg is None or type_value is None or not CONTENT_TYPE_PATTERN.match(type_value):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTENT_TYPE_FORMAT",
                    message="content_type is required and must be a lowercase snake_case token",
                    span=(type_arg.span if type_arg is not None else step.span),
                    node_id=step.id,
                )
            )
            return diagnostics

        if type_arg is not None and type_value is not None and kind_value in CONTENT_KIND_WHITELIST:
            classification = parse_content_classification(kind_result.value, type_result.value)
            if classification is None:
                diagnostics.extend(
                    content_type_value_diagnostics(
                        kind_value=kind_value,
                        type_value=type_value,
                        span=type_arg.span or step.span,
                        node_id=step.id,
                        compat_mode=compat_mode,
                    )
                )
        elif type_arg is not None and type_value is not None and kind_value in KNOWN_CONTENT_KINDS:
            diagnostics.extend(
                content_type_value_diagnostics(
                    kind_value=kind_value,
                    type_value=type_value,
                    span=type_arg.span or step.span,
                    node_id=step.id,
                    compat_mode=compat_mode,
                )
            )
        return diagnostics

    @staticmethod
    def validate_alloc_container_call(
        call: IRCall,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        node_id: str | None,
        content_whitelist_mode: str,
        content_type_policy: str,
        scope: ContentArgumentScope | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        scope = scope or ContentArgumentScope(literal_bindings, expr_bindings)
        kind_arg = find_arg_by_name(call.args, "kind")
        kind_result = ContentArgumentResolver.resolve_argument(kind_arg.value if kind_arg else None, ContainerKind, scope)
        kind_value = kind_result.token
        diagnostics.extend(content_enum_diagnostics(kind_result, span=kind_arg.value.span if kind_arg else call.span, node_id=node_id))
        if kind_arg is not None and kind_value is not None and kind_value not in CONTAINER_KIND_WHITELIST:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTAINER_KIND",
                    message=f"Unsupported container kind '{kind_value}'",
                    span=kind_arg.span or call.span,
                    node_id=node_id,
                )
            )
        diagnostics.extend(
            ConstructorValidator.validate_surface_capacity_forbidden(
                kind_value=kind_value,
                capacity_arg=find_arg_by_name(call.args, "capacity"),
                span=call.span,
                node_id=node_id,
            )
        )

        load_arg = find_arg_by_name(call.args, "load")
        if load_arg is None:
            return diagnostics
        load_value = ExprResolver.resolve_bound_expr(load_arg.value, expr_bindings)
        if not isinstance(load_value, IRList):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_LOAD_ITEM",
                    message="constructor load must be a list of content_spec:quantity items",
                    span=load_arg.span or call.span,
                    node_id=node_id,
                )
            )
            return diagnostics

        for item in load_value.elements:
            if not isinstance(item, IRPair) or not isinstance(item.left, IRCall) or item.left.name != "DefineContent":
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_LOAD_ITEM",
                        message="constructor load items must be content_spec:quantity pairs",
                        span=item.span or load_arg.span or call.span,
                        node_id=node_id,
                    )
                )
                continue
            diagnostics.extend(
                ConstructorValidator.validate_define_content_call(
                    item.left,
                    literal_bindings=literal_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                    scope=scope,
                )
            )
        return diagnostics

    @staticmethod
    def validate_surface_capacity_forbidden(
        *,
        kind_value: str | None,
        capacity_arg,
        span,
        node_id: str | None,
    ) -> list[Diagnostic]:
        if kind_value != ContainerKind.SURFACE.value or capacity_arg is None:
            return []
        return [
            Diagnostic(
                code="SEM_SURFACE_CAPACITY_FORBIDDEN",
                message="surface constructor does not support volume capacity",
                span=(capacity_arg.span if getattr(capacity_arg, "span", None) is not None else span),
                node_id=node_id,
            )
        ]

    @staticmethod
    def validate_define_content_call(
        call: IRCall,
        *,
        literal_bindings: dict[str, Any],
        node_id: str | None,
        content_whitelist_mode: str,
        content_type_policy: str,
        scope: ContentArgumentScope | None = None,
    ) -> list[Diagnostic]:
        diagnostics = OperationContractValidator.validate_argument_names(
            call,
            node_id=node_id,
            allowed_args=BUILTIN_OPERATION_SPECS["DefineContent"].allowed_args,
        )
        if diagnostics:
            return diagnostics
        step = IRStep(
            id=node_id or "<call>",
            name="DefineContent",
            args=call.args,
            span=call.span,
        )
        return ConstructorValidator.validate_container_content_constructor_semantics(
            step,
            literal_bindings,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
            scope=scope,
        )


def find_arg(step: IRStep, name: str):
    for arg in step.args:
        if arg.name == name:
            return arg
    return None


def find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def content_type_value_diagnostics(
    *,
    kind_value: str,
    type_value: str,
    span,
    node_id: str | None,
    compat_mode: bool,
) -> list[Diagnostic]:
    compatibility_diagnostics = content_syntax.normalization_diagnostics(
        kind_value=kind_value,
        type_value=type_value,
        span=span,
        node_id=node_id,
        compat_mode=compat_mode,
    )
    if compatibility_diagnostics:
        return compatibility_diagnostics
    return [
        Diagnostic(
            code="SEM_INVALID_CONTENT_TYPE_VALUE",
            message=(
                f"Unsupported content_type '{type_value}' for kind '{kind_value}'; "
                "use a canonical token for that content kind or its canonical other_* fallback"
            ),
            span=span,
            node_id=node_id,
        )
    ]
