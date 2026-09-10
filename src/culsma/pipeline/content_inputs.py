"""Scope-aware content input resolution shared by semantic and type checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import AbstractSet, Any, Mapping

from culsma.common.content_contracts import CONTENT_ENUM_TYPES, resolve_content_enum_member
from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.compat.content_syntax import resolve_legacy_content_token
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRRecord, IRString


class ContentResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    INVALID = "invalid"


class ContentInputSource(StrEnum):
    ENUM = "enum"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


class ContentResolutionIssue(StrEnum):
    UNKNOWN_MEMBER = "unknown_member"
    WRONG_ENUM_TYPE = "wrong_enum_type"
    NON_TEXT = "non_text"
    CYCLIC_BINDING = "cyclic_binding"


@dataclass(frozen=True)
class ContentArgumentScope:
    literal_bindings: Mapping[str, Any] = field(default_factory=dict)
    expr_bindings: Mapping[str, Any] = field(default_factory=dict)
    defined_names: AbstractSet[str] = frozenset()

    def has_binding(self, name: str) -> bool:
        return name in self.literal_bindings or name in self.expr_bindings or name in self.defined_names


@dataclass(frozen=True)
class ContentEnumResolution:
    status: ContentResolutionStatus
    value: StrEnum | str | None = None
    source: ContentInputSource = ContentInputSource.UNKNOWN
    issue: ContentResolutionIssue | None = None
    detail: str = ""
    expected_enum: type[StrEnum] | None = None

    @property
    def token(self) -> str | None:
        if self.status is not ContentResolutionStatus.RESOLVED:
            return None
        return self.value.value if isinstance(self.value, StrEnum) else self.value


class ContentArgumentResolver:
    @staticmethod
    def resolve_argument(
        expr: Any,
        expected_enum: type[StrEnum] | None,
        scope: ContentArgumentScope,
        seen_names: frozenset[str] = frozenset(),
    ) -> ContentEnumResolution:
        if isinstance(expr, StrEnum):
            return ContentArgumentResolver.resolve_enum_value(expr, expected_enum)
        if isinstance(expr, IRString) or isinstance(expr, str):
            return ContentEnumResolution(
                ContentResolutionStatus.RESOLVED,
                resolve_legacy_content_token(expr),
                ContentInputSource.LEGACY,
                expected_enum=expected_enum,
            )
        if isinstance(expr, IRIdentifier):
            return ContentArgumentResolver.resolve_binding(expr.name, expected_enum, scope, seen_names)
        if isinstance(expr, IRMember):
            return ContentArgumentResolver.resolve_enum_member(expr, expected_enum, scope, seen_names)
        if expr is None:
            return ContentEnumResolution(ContentResolutionStatus.DEFERRED, expected_enum=expected_enum)
        return ContentEnumResolution(
            ContentResolutionStatus.INVALID,
            issue=ContentResolutionIssue.NON_TEXT,
            expected_enum=expected_enum,
        )

    @staticmethod
    def resolve_enum_value(value: StrEnum, expected_enum: type[StrEnum] | None) -> ContentEnumResolution:
        if type(value) not in CONTENT_ENUM_TYPES.values() or (
            expected_enum is not None and type(value) is not expected_enum
        ):
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID, value, ContentInputSource.ENUM,
                ContentResolutionIssue.WRONG_ENUM_TYPE, type(value).__name__,
                expected_enum=expected_enum,
            )
        return ContentEnumResolution(
            ContentResolutionStatus.RESOLVED, value, ContentInputSource.ENUM,
            expected_enum=expected_enum,
        )

    @staticmethod
    def resolve_binding(
        name: str,
        expected_enum: type[StrEnum] | None,
        scope: ContentArgumentScope,
        seen_names: frozenset[str] = frozenset(),
    ) -> ContentEnumResolution:
        if name in seen_names:
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID,
                issue=ContentResolutionIssue.CYCLIC_BINDING, detail=name,
                expected_enum=expected_enum,
            )
        seen_names = seen_names | {name}
        if name in scope.literal_bindings:
            value = scope.literal_bindings[name]
        elif name in scope.expr_bindings:
            value = scope.expr_bindings[name]
        elif name in scope.defined_names:
            return ContentEnumResolution(ContentResolutionStatus.DEFERRED, expected_enum=expected_enum)
        else:
            return ContentEnumResolution(
                ContentResolutionStatus.RESOLVED, resolve_legacy_content_token(IRIdentifier(name)),
                ContentInputSource.LEGACY, expected_enum=expected_enum,
            )
        return ContentArgumentResolver.resolve_argument(value, expected_enum, scope, seen_names)

    @staticmethod
    def resolve_enum_member(
        expr: IRMember,
        expected_enum: type[StrEnum] | None,
        scope: ContentArgumentScope,
        seen_names: frozenset[str] = frozenset(),
    ) -> ContentEnumResolution:
        if not isinstance(expr.base, IRIdentifier):
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID, issue=ContentResolutionIssue.NON_TEXT,
                expected_enum=expected_enum,
            )
        name = expr.base.name
        if scope.has_binding(name):
            # A local name shadows the enum namespace. Resolve records as records.
            if name in seen_names:
                return ContentEnumResolution(
                    ContentResolutionStatus.INVALID,
                    issue=ContentResolutionIssue.CYCLIC_BINDING, detail=name,
                    expected_enum=expected_enum,
                )
            base = scope.expr_bindings.get(name, scope.literal_bindings.get(name))
            if isinstance(base, IRRecord) and expr.member in base.entries:
                return ContentArgumentResolver.resolve_argument(
                    base.entries[expr.member], expected_enum, scope, seen_names | {name},
                )
            if base is None:
                return ContentEnumResolution(ContentResolutionStatus.DEFERRED, expected_enum=expected_enum)
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID, issue=ContentResolutionIssue.NON_TEXT,
                detail=name, expected_enum=expected_enum,
            )
        enum_type = CONTENT_ENUM_TYPES.get(name)
        if enum_type is None:
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID, issue=ContentResolutionIssue.NON_TEXT,
                detail=name, expected_enum=expected_enum,
            )
        value = resolve_content_enum_member(enum_type, expr.member)
        if value is None:
            return ContentEnumResolution(
                ContentResolutionStatus.INVALID, source=ContentInputSource.ENUM,
                issue=ContentResolutionIssue.UNKNOWN_MEMBER, detail=f"{name}.{expr.member}",
                expected_enum=expected_enum,
            )
        return ContentArgumentResolver.resolve_enum_value(value, expected_enum)


def content_enum_diagnostics(
    result: ContentEnumResolution, *, span: Span | None, node_id: str | None,
) -> list[Diagnostic]:
    """Translate semantic resolution failures without emitting typecheck errors."""
    if result.issue is ContentResolutionIssue.UNKNOWN_MEMBER:
        return [Diagnostic(
            code="SEM_CONTENT_ENUM_MEMBER_INVALID",
            message=f"Unknown content enum member '{result.detail}'",
            span=span, node_id=node_id,
        )]
    if result.issue is ContentResolutionIssue.CYCLIC_BINDING:
        return [Diagnostic(
            code="SEM_CONTENT_ENUM_BINDING_CYCLE",
            message=f"Cyclic content binding at '{result.detail}'",
            span=span, node_id=node_id,
        )]
    return []
