"""Statement-level semantic validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.ir_nodes import (
    IRArg,
    IRAssign,
    IRCall,
    IRLet,
    IRMutation,
    IRPair,
    IRQuantity,
    IRStatement,
    IRStep,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.operation_specs import OperationSpec
from culsma.pipeline.program_registry import get_separation_slot_contract

from .binding import BindingValidator
from .constructors import ConstructorValidator
from .context import _GroupBinding
from .expression_contracts import validate_expr_contracts
from .material_transition import validate_material_transitions_contract
from .operations import OperationContractValidator
from .resolution import ExprResolver
from .separation import validate_component_fates_contract

BUILTIN_METHOD_STEPS = {"append"}
CONSTRAINT_CUSTOMIZED = "customized"
COLD_CHAIN_MAX_C = 8.0
AGIT_MODES = {"vortex", "invert", "shake", "stir"}
READOUT_QUANTITY_SETS = {
    "img": frozenset({"uv_absorbance", "fluorescence", "colorimetric", "customized"}),
    "ecp": frozenset({"ph", "conductivity", "dissolved_oxygen", "orp", "customized"}),
    "phy": frozenset({"temperature", "pressure", "flow_rate", "mass", "volume", "humidity", "current", "customized"}),
}


@dataclass(frozen=True)
class _RequirementSpec:
    category: str
    allowed_on: frozenset[str]
    scopes: frozenset[str]
    conflicts: frozenset[str] = frozenset()
    needs_context: frozenset[str] = frozenset()


REQUIREMENT_REGISTRY: dict[str, _RequirementSpec] = {
    "preserve_boundary": _RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "preserve_layering": _RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "preserve_fraction_order": _RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "aseptic": _RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "low_carryover": _RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "cross_contam_control": _RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "gentle": _RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "avoid_resuspension": _RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "avoid_shear": _RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "preserve_viability": _RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "cold_chain": _RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "sep", "frac", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "dark_protected": _RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "controlled_atmosphere": _RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "high_precision": _RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "low_loss": _RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "quantitative_recovery": _RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "stabilized_reading": _RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "low_noise": _RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    "noninvasive": _RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ),
    CONSTRAINT_CUSTOMIZED: _RequirementSpec(
        category="customized",
        allowed_on=frozenset({"mutation", "sep", "frac", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ),
}


def validate_assign_target_contract(
    stmt: IRAssign,
    *,
    expr_bindings: dict[str, Any],
    defined_names: set[str],
) -> list[Diagnostic]:
    root = BindingValidator.assign_target_root_name(stmt.target)
    if root is None:
        return [
            Diagnostic(
                code="VAL_ASSIGN_TARGET_INVALID",
                message="Assignment target must be a local name or member path rooted at a local name",
                span=stmt.span,
                node_id=stmt.id,
            )
        ]
    if root not in defined_names and root not in expr_bindings:
        return [
            Diagnostic(
                code="VAL_ASSIGN_TARGET_UNBOUND",
                message=f"Assignment target root '{root}' is not bound in the current scope",
                span=stmt.span,
                node_id=stmt.id,
            )
        ]
    return []


def validate_agit_contract(step: IRStep, *, literal_bindings: dict[str, Any]) -> list[Diagnostic]:
    if step.name != "agit":
        return []

    diagnostics: list[Diagnostic] = []
    mode_arg = _find_arg(step, "mode")
    if mode_arg is None:
        return diagnostics

    mode_value = ExprResolver.to_name_ref(mode_arg.value, literal_bindings)
    if mode_value is None or mode_value not in AGIT_MODES:
        diagnostics.append(
            Diagnostic(
                code="SEM_AGIT_MODE_UNKNOWN",
                message="agit(...): mode must be one of vortex, invert, shake, stir",
                span=mode_arg.span or step.span,
                node_id=step.id,
            )
        )
        return diagnostics

    duration_arg = _find_arg(step, "duration")
    rate_arg = _find_arg(step, "rate")
    cycles_arg = _find_arg(step, "cycles")

    if mode_value == "invert":
        if duration_arg is not None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_AGIT_ARG_CONFLICT",
                    message="agit(mode = invert): duration is not allowed; use cycles",
                    span=duration_arg.span or step.span,
                    node_id=step.id,
                )
            )
        if rate_arg is not None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_AGIT_ARG_CONFLICT",
                    message="agit(mode = invert): rate is not allowed; use cycles",
                    span=rate_arg.span or step.span,
                    node_id=step.id,
                )
            )
    else:
        if cycles_arg is not None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_AGIT_ARG_CONFLICT",
                    message=f"agit(mode = {mode_value}): cycles is not allowed; use duration/rate",
                    span=cycles_arg.span or step.span,
                    node_id=step.id,
                )
            )
    return diagnostics


def defined_names_from_step(stmt: IRStep, literal_bindings: dict[str, Any], expr_bindings: dict[str, Any]) -> set[str]:
    del stmt, literal_bindings, expr_bindings
    return set()


def _find_arg(step: IRStep, name: str):
    for arg in step.args:
        if arg.name == name:
            return arg
    return None


def _find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def validate_with_constraint_contract(
    stmt: IRWithConstraint,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not stmt.statements:
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_BODY_REQUIRED",
                message="with constraint(...): at least one statement is required",
                span=stmt.span,
                node_id=stmt.id,
            )
        )
    if not stmt.requirements and not stmt.options:
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_ITEM_REQUIRED",
                message="with constraint(...): at least one requirement or option is required",
                span=stmt.span,
                node_id=stmt.id,
            )
        )
    requirement_names = dedupe_requirement_names(stmt.requirements)
    option_names = [arg.name for arg in stmt.options]
    seen_options: set[str] = set()
    duplicate_options: list[str] = []
    for name in option_names:
        if name in seen_options and name not in duplicate_options:
            duplicate_options.append(name)
        seen_options.add(name)
    for dup in duplicate_options:
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_DUPLICATE_OPTION",
                message=f"constraint option '{dup}' is duplicated",
                span=stmt.span,
                node_id=stmt.id,
            )
        )

    unknown_requirements = [name for name in requirement_names if name not in REQUIREMENT_REGISTRY]
    for name in unknown_requirements:
        diagnostics.append(
            Diagnostic(
                code="SEM_UNKNOWN_REQUIREMENT",
                message=f"Unknown requirement '{name}' in constraint(...)",
                span=stmt.span,
                node_id=stmt.id,
            )
        )

    for name in requirement_names:
        spec = REQUIREMENT_REGISTRY.get(name)
        if spec is None:
            continue
        if "block" not in spec.scopes:
            diagnostics.append(
                Diagnostic(
                    code="SEM_CONSTRAINT_SCOPE_INVALID",
                    message=f"Requirement '{name}' is not allowed in block constraint scope",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
    for name in requirement_names:
        spec = REQUIREMENT_REGISTRY.get(name)
        if spec is None:
            continue
        for conflict in spec.conflicts:
            if conflict in requirement_names:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_CONSTRAINT_CONFLICT",
                        message=f"Requirement '{name}' conflicts with '{conflict}'",
                        span=stmt.span,
                        node_id=stmt.id,
                    )
                )

    if CONSTRAINT_CUSTOMIZED in requirement_names and len(requirement_names) > 1:
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_CUSTOMIZED_EXCLUSIVE",
                message="constraint(customized, ...): customized must not be mixed with standard requirements",
                span=stmt.span,
                node_id=stmt.id,
            )
        )

    if CONSTRAINT_CUSTOMIZED in requirement_names:
        schema_arg = _find_arg_by_name(stmt.options, "schema_ref")
        if schema_arg is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_CONSTRAINT_CUSTOMIZED_SCHEMA_REQUIRED",
                    message="constraint(customized, ...): schema_ref is required",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
        for arg in stmt.options:
            if arg.name != "schema_ref":
                diagnostics.append(
                    Diagnostic(
                        code="SEM_CONSTRAINT_UNKNOWN_OPTION",
                        message=f"constraint(customized, ...): unknown option '{arg.name}'",
                        span=arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
        if schema_arg is not None:
            diagnostics.extend(
                validate_expr_contracts(
                    schema_arg.value,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    group_bindings={},
                    node_id=stmt.id,
                    content_whitelist_mode="strict",
                    content_type_policy="required",
                )
            )
    elif stmt.options:
        for arg in stmt.options:
            diagnostics.append(
                Diagnostic(
                    code="SEM_CONSTRAINT_UNKNOWN_OPTION",
                    message=f"constraint(...): option '{arg.name}' is not supported for standard requirements",
                    span=arg.span or stmt.span,
                    node_id=stmt.id,
                )
            )
    return diagnostics


def dedupe_requirement_names(names: tuple[str, ...] | list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _classify_constraint_action_family(stmt: IRStatement) -> str | None:
    if isinstance(stmt, IRMutation):
        return "mutation"
    if isinstance(stmt, IRStep):
        if stmt.name in {"sep", "frac", "img", "ecp", "phy"}:
            return stmt.name
        return None
    if isinstance(stmt, IRLet) and isinstance(stmt.value, IRCall):
        if stmt.value.name in {"sep", "frac", "img", "ecp", "phy", "stream"}:
            return stmt.value.name
    return None


def validate_active_constraint_compatibility(
    stmt: IRStatement,
    *,
    active_requirements: tuple[str, ...],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    family = _classify_constraint_action_family(stmt)
    if family is None:
        return diagnostics
    for name in dedupe_requirement_names(active_requirements):
        spec = REQUIREMENT_REGISTRY.get(name)
        if spec is None or family in spec.allowed_on:
            continue
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH",
                message=f"Requirement '{name}' is not allowed on action family '{family}'",
                span=stmt.span,
                node_id=getattr(stmt, "id", None),
            )
        )
    return diagnostics


def validate_active_env_constraint_compatibility(
    stmt: IRWithEnv,
    *,
    expr_bindings: dict[str, Any],
    active_requirements: tuple[str, ...],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if "cold_chain" not in active_requirements:
        return diagnostics
    thermal_arg = _find_arg_by_name(stmt.env_args, "thermal")
    if thermal_arg is None:
        return diagnostics
    thermal_value = ExprResolver.resolve_bound_expr(thermal_arg.value, expr_bindings)
    if not isinstance(thermal_value, IRQuantity):
        return diagnostics
    if thermal_value.unit != "C":
        return diagnostics
    if float(thermal_value.value) > COLD_CHAIN_MAX_C:
        diagnostics.append(
            Diagnostic(
                code="SEM_CONSTRAINT_ENV_CONFLICT",
                message=(
                    f"Requirement 'cold_chain' conflicts with env thermal {thermal_value.value}{thermal_value.unit}"
                ),
                span=thermal_arg.span or stmt.span,
                node_id=stmt.id,
            )
        )
    return diagnostics


def validate_mutation_contract(
    stmt: IRMutation,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
    group_bindings: dict[str, _GroupBinding],
) -> list[Diagnostic]:
    del literal_bindings, expr_bindings, group_bindings
    diagnostics: list[Diagnostic] = []
    has_quantified = any(isinstance(source, IRPair) for source in stmt.sources)
    has_unquantified = any(not isinstance(source, IRPair) for source in stmt.sources)
    if has_quantified and has_unquantified:
        diagnostics.append(
            Diagnostic(
                code="SEM_MUTATION_QUANTITY_STYLE_CONFLICT",
                message="mutation_stmt source list must not mix quantified and unquantified items",
                span=stmt.span,
                node_id=stmt.id,
            )
        )
        return diagnostics
    return diagnostics


def validate_let_call_contract(
    stmt: IRLet,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
    operations: Mapping[str, OperationSpec],
    content_whitelist_mode: str,
    content_type_policy: str,
) -> list[Diagnostic]:
    value = stmt.value
    if not isinstance(value, IRCall):
        return []
    if value.name == "DefineContent":
        diagnostics = ConstructorValidator.validate_define_content_call(
            value,
            literal_bindings=literal_bindings,
            node_id=stmt.id,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )
        diagnostics.append(
            Diagnostic(
                code="SEM_STANDALONE_CONTENT_INIT_FORBIDDEN",
                message="standalone content constructor is not allowed in protocol execution flow",
                span=stmt.span,
                node_id=stmt.id,
            )
        )
        return diagnostics
    if value.name == "Measure":
        return [
            Diagnostic(
                code="SEM_MEASURE_STDLIB_ROUTE_UNSUPPORTED",
                message="let-bound Measure(...) is outside the current stdlib scope; use img/ecp/phy directly",
                span=stmt.span,
                node_id=stmt.id,
            )
        ]
    if value.name != "AllocContainer":
        diagnostics = OperationContractValidator.validate_call(
            value,
            node_id=stmt.id,
            operations=operations,
        )
        diagnostics.extend(
            validate_readout_schema_contract(
                value.name,
                value.args,
                literal_bindings=literal_bindings,
                node_id=stmt.id,
                span=value.span,
            )
        )
        if value.name == "sep":
            diagnostics.extend(
                validate_component_fates_contract(
                    value.args,
                    expr_bindings=expr_bindings,
                    node_id=stmt.id,
                    span=value.span,
                )
            )
            program_arg = _find_arg_by_name(value.args, "program")
            program = (
                ExprResolver.resolve_call_expr(program_arg.value, expr_bindings)
                if program_arg is not None
                else None
            )
            diagnostics.extend(
                validate_material_transitions_contract(
                    value.args,
                    expr_bindings=expr_bindings,
                    output_contract=(
                        get_separation_slot_contract(program.name)
                        if isinstance(program, IRCall)
                        else None
                    ),
                    node_id=stmt.id,
                    span=value.span,
                )
            )
        return diagnostics
    diagnostics = OperationContractValidator.validate_call(
        value,
        node_id=stmt.id,
        operations=operations,
    )
    diagnostics.extend(
        ConstructorValidator.validate_alloc_container_call(
            value,
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
            node_id=stmt.id,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )
    )
    return diagnostics


def validate_readout_schema_contract(
    call_name: str,
    args: list[IRArg],
    *,
    literal_bindings: dict[str, Any],
    node_id: str | None,
    span: Span | None,
) -> list[Diagnostic]:
    if call_name not in {"img", "ecp", "phy"}:
        return []
    quantity_arg = _find_arg_by_name(args, "quantity")
    if quantity_arg is None:
        return []
    quantity_value = ExprResolver.to_text_token(quantity_arg.value, literal_bindings)
    allowed_quantities = READOUT_QUANTITY_SETS[call_name]
    if quantity_value not in allowed_quantities:
        return [
            Diagnostic(
                code="SEM_INVALID_READOUT_QUANTITY",
                message=(
                    f"Readout '{call_name}' quantity must be one of: "
                    + ", ".join(sorted(allowed_quantities))
                ),
                span=quantity_arg.span or span,
                node_id=node_id,
            )
        ]
    if quantity_value != "customized":
        return []
    if _find_arg_by_name(args, "schema_ref") is not None:
        return []
    return [
        Diagnostic(
            code="SEM_MISSING_REQUIRED_ARG",
            message=f"Missing required arg 'schema_ref' in call '{call_name}' when quantity = customized",
            span=quantity_arg.span or span,
            node_id=node_id,
        )
    ]
