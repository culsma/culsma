"""Plan-owned traversal and diagnostics for external parameter contracts."""
from dataclasses import replace
from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER


def normalize_external_plan_tree(value):
    if isinstance(value, PlanStep):
        return replace(value, args=DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_plan_arguments(
            value.op, {key: normalize_external_plan_tree(item) for key, item in value.args.items()}))
    if isinstance(value, list):
        return [normalize_external_plan_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_external_plan_tree(item) for key, item in value.items()}
    return value


def normalize_external_plan(plan: PlanProgram) -> PlanProgram:
    if any(d.code == 'PLAN_PLATE_SELECTOR_INVALID' and d.severity == 'error' for d in plan.diagnostics):
        return replace(plan, plans=[])
    try:
        return replace(plan, plans=[replace(protocol, steps=[normalize_external_plan_tree(step) for step in protocol.steps]) for protocol in plan.plans])
    except (TypeError, ValueError) as error:
        return replace(plan, plans=[], diagnostics=[*plan.diagnostics, Diagnostic(
            code='PLAN_EXTERNAL_ENUM_INVALID', message=str(error), span=plan.span,
        )])
