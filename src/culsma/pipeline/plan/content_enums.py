"""Validate statically bound content inputs; dynamic values are checked at runtime."""

from typing import Any

from culsma.common.content_contracts import ContainerKind, ContentKind, ContentType
from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.content_boundary import read_bound_content_token, resolve_bound_content_classification, resolve_bound_container_kind
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep


def is_deferred_content_input(value: Any) -> bool:
    return isinstance(value, dict) and value.get('kind') in {'IRIdentifier', 'IRMember', 'IRIndex', 'IRCall', 'IRBinary'}


def validate_bound_content_step(step: PlanStep) -> list[Diagnostic]:
    try:
        if step.op == 'DefineContent':
            kind, content_type = step.args.get('kind'), step.args.get('type')
            for value, expected in ((kind, ContentKind), (content_type, ContentType)):
                if not is_deferred_content_input(value):
                    read_bound_content_token(value, expected)
            if not is_deferred_content_input(kind) and not is_deferred_content_input(content_type):
                resolve_bound_content_classification(kind, content_type)
        elif step.op == 'AllocContainer' and 'kind' in step.args:
            value = step.args['kind']
            if not is_deferred_content_input(value):
                kind = resolve_bound_container_kind(value)
                if kind is ContainerKind.SURFACE and step.args.get('capacity') is not None:
                    raise ValueError('surface constructor does not support volume capacity')
    except ValueError as error:
        code = 'PLAN_CONTENT_CLASSIFICATION_INVALID' if step.op == 'DefineContent' else 'PLAN_CONTAINER_KIND_INVALID'
        return [Diagnostic(code=code, message=str(error), span=step.span, node_id=step.step_id)]
    return []


def validate_bound_content_steps(value: Any) -> list[Diagnostic]:
    if isinstance(value, PlanStep):
        return validate_bound_content_step(value) + validate_bound_content_steps(value.args)
    if isinstance(value, dict):
        return [d for item in value.values() for d in validate_bound_content_steps(item)]
    if isinstance(value, list):
        return [d for item in value for d in validate_bound_content_steps(item)]
    return []


def validate_bound_content_plan(plan: PlanProgram) -> PlanProgram:
    diagnostics = [d for protocol in plan.plans for d in validate_bound_content_steps(protocol.steps)]
    if not diagnostics:
        return plan
    return PlanProgram(plans=[], diagnostics=[*plan.diagnostics, *diagnostics], span=plan.span)
