"""Public content argument resolution contracts, without pipeline traversal."""

from __future__ import annotations

from enum import StrEnum

import pytest

from culsma.common.content_contracts import (
    ContainerKind, ContentKind, ContentType, resolve_content_enum_member,
)
from culsma.pipeline import content_vocab
from culsma.pipeline.compat.content_syntax import resolve_legacy_content_token
from culsma.pipeline.content_inputs import (
    ContentArgumentResolver, ContentArgumentScope, ContentEnumResolution,
    ContentInputSource, ContentResolutionIssue, ContentResolutionStatus, content_enum_diagnostics,
)
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRQuantity, IRRecord, IRString
from culsma.pipeline.plan.content_enums import (
    contains_member_expression, guard_content_enum_execution, has_unlowered_content_enum,
)
from culsma.pipeline.plan_nodes import PlanProgram


def member(namespace="ContentKind", name="FORMULATION"):
    return IRMember(base=IRIdentifier(namespace), member=name)


def test_old_imports_preserve_enum_identity():
    assert content_vocab.ContentKind is ContentKind
    assert content_vocab.ContentType is ContentType
    assert content_vocab.ContainerKind is ContainerKind
    assert resolve_content_enum_member(ContentKind, "FORMULATION") is ContentKind.FORMULATION
    assert resolve_content_enum_member(ContentKind, "formulation") is None


@pytest.mark.parametrize(
    ("expr", "scope", "status", "value", "issue"),
    [
        (member(), ContentArgumentScope(), ContentResolutionStatus.RESOLVED, ContentKind.FORMULATION, None),
        (ContentKind.FORMULATION, ContentArgumentScope(), ContentResolutionStatus.RESOLVED, ContentKind.FORMULATION, None),
        (IRString("formulation"), ContentArgumentScope(), ContentResolutionStatus.RESOLVED, "formulation", None),
        (IRIdentifier("formulation"), ContentArgumentScope(), ContentResolutionStatus.RESOLVED, "formulation", None),
        (IRIdentifier("k"), ContentArgumentScope(expr_bindings={"k": member()}), ContentResolutionStatus.RESOLVED, ContentKind.FORMULATION, None),
        (IRIdentifier("k"), ContentArgumentScope(expr_bindings={"k": IRIdentifier("v"), "v": member()}), ContentResolutionStatus.RESOLVED, ContentKind.FORMULATION, None),
        (IRIdentifier("k"), ContentArgumentScope(literal_bindings={"k": ContentKind.CHEMICAL}, expr_bindings={"k": member()}), ContentResolutionStatus.RESOLVED, ContentKind.CHEMICAL, None),
        (IRIdentifier("k"), ContentArgumentScope(defined_names={"k"}), ContentResolutionStatus.DEFERRED, None, None),
        (None, ContentArgumentScope(), ContentResolutionStatus.DEFERRED, None, None),
        (member(), ContentArgumentScope(defined_names={"ContentKind"}), ContentResolutionStatus.DEFERRED, None, None),
        (member(), ContentArgumentScope(literal_bindings={"ContentKind": "shadow"}), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.NON_TEXT),
        (IRQuantity(3, None), ContentArgumentScope(), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.NON_TEXT),
        (IRIdentifier("k"), ContentArgumentScope(expr_bindings={"k": IRIdentifier("v"), "v": IRIdentifier("k")}), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.CYCLIC_BINDING),
        (member(name="TYPO"), ContentArgumentScope(), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.UNKNOWN_MEMBER),
        (member("ContentType", "MEDIUM"), ContentArgumentScope(), ContentResolutionStatus.INVALID, ContentType.MEDIUM, ContentResolutionIssue.WRONG_ENUM_TYPE),
        (member("Unknown", "FORMULATION"), ContentArgumentScope(), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.NON_TEXT),
        (IRMember(base=IRQuantity(3, None), member="FORMULATION"), ContentArgumentScope(), ContentResolutionStatus.INVALID, None, ContentResolutionIssue.NON_TEXT),
        (member("settings", "kind"), ContentArgumentScope(expr_bindings={"settings": IRRecord(entries={"kind": member()})}), ContentResolutionStatus.RESOLVED, ContentKind.FORMULATION, None),
    ],
)
def test_public_argument_resolver(expr, scope, status, value, issue):
    result = ContentArgumentResolver.resolve_argument(expr, ContentKind, scope)
    assert result.expected_enum is ContentKind
    assert result.status is status
    assert result.issue is issue
    if isinstance(value, StrEnum):
        assert result.value is value
    else:
        assert result.value == value
    assert result.token == (str(value) if status is ContentResolutionStatus.RESOLVED else None)


def test_public_member_and_binding_resolvers():
    scope = ContentArgumentScope(expr_bindings={"k": member()})
    assert scope.has_binding("k")
    assert not scope.has_binding("ContentKind")
    assert ContentArgumentResolver.resolve_enum_member(member(), ContentKind, scope).value is ContentKind.FORMULATION
    assert ContentArgumentResolver.resolve_binding("k", ContentKind, scope).value is ContentKind.FORMULATION
    assert ContentArgumentResolver.resolve_binding("k", ContentKind, scope, frozenset({"k"})).issue is ContentResolutionIssue.CYCLIC_BINDING


def test_foreign_string_enum_is_not_accepted_as_content_enum():
    class Other(StrEnum):
        FORMULATION = "formulation"
    result = ContentArgumentResolver.resolve_enum_value(Other.FORMULATION, ContentKind)
    assert result.issue is ContentResolutionIssue.WRONG_ENUM_TYPE
    assert result.token is None


@pytest.mark.parametrize(("value", "expected"), [
    (IRString("medium"), "medium"), (IRIdentifier("medium"), "medium"),
    ("medium", "medium"), (3, None),
])
def test_legacy_token_admission_is_owned_by_compat(value, expected):
    assert resolve_legacy_content_token(value) == expected


@pytest.mark.parametrize(
    ("issue", "code"),
    [(ContentResolutionIssue.UNKNOWN_MEMBER, "SEM_CONTENT_ENUM_MEMBER_INVALID"),
     (ContentResolutionIssue.CYCLIC_BINDING, "SEM_CONTENT_ENUM_BINDING_CYCLE"),
     (ContentResolutionIssue.WRONG_ENUM_TYPE, None), (ContentResolutionIssue.NON_TEXT, None)],
)
def test_diagnostic_phase_ownership(issue, code):
    result = ContentEnumResolution(ContentResolutionStatus.INVALID, issue=issue, detail="example")
    diagnostics = content_enum_diagnostics(result, span=None, node_id="n")
    assert [d.code for d in diagnostics] == ([] if code is None else [code])
    assert all(d.node_id == "n" for d in diagnostics)


@pytest.mark.parametrize(
    ("payload", "blocked"),
    [
        ({"kind": "IRMember", "base": {"kind": "IRIdentifier", "name": "ContentKind"}, "member": "FORMULATION"}, True),
        ({"kind": "IRMember", "base": {"kind": "IRIdentifier", "name": "MaterialRelation"}, "member": "FREE"}, False),
        ({"op": "DefineContent", "args": {"kind": {"kind": "IRMember", "base": {}, "member": "kind"}}}, True),
        ({"kind": "IRCall", "name": "AllocContainer", "args": [{"name": "kind", "value": {"kind": "IRMember"}}]}, True),
        ([{"op": "DefineContent", "args": {"kind": "formulation", "type": "medium"}}], False),
        ({"op": "Other", "args": {"kind": {"kind": "IRMember"}}}, False),
    ],
)
def test_execution_boundary_payload_detection(payload, blocked):
    assert has_unlowered_content_enum(payload) is blocked
    assert has_unlowered_content_enum([payload]) is blocked


def test_public_execution_guard_preserves_legacy_plan():
    assert contains_member_expression([{"nested": {"kind": "IRMember"}}])
    assert not contains_member_expression({"value": "medium"})
    plan = PlanProgram()
    assert guard_content_enum_execution(plan) is plan
