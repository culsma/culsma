"""Statement-level semantic validation dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, cast

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.analysis import CompileAnalysis, ProtocolAnalysis
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRCall,
    IRConditional,
    IRControl,
    IRIdentifier,
    IRInclude,
    IRLet,
    IRMutation,
    IRPair,
    IRRepeat,
    IRStatement,
    IRStep,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.operation_specs import OperationSpec

from .binding import BindingValidator
from .constructors import ConstructorValidator
from .context import _GroupBinding
from .environment import EnvContractValidator
from .expression_contracts import validate_expr_contracts
from .groups import GroupIndexValidator
from .statement_contracts import (
    BUILTIN_METHOD_STEPS,
    dedupe_requirement_names,
    defined_names_from_step,
    validate_active_constraint_compatibility,
    validate_active_env_constraint_compatibility,
    validate_agit_contract,
    validate_assign_target_contract,
    validate_let_call_contract,
    validate_mutation_contract,
    validate_readout_schema_contract,
    validate_with_constraint_contract,
)


@dataclass
class StatementValidationContext:
    literal_bindings: dict[str, Any]
    expr_bindings: dict[str, Any]
    group_bindings: dict[str, _GroupBinding]
    defined_names: set[str]
    active_requirements: tuple[str, ...]
    diagnostics: list[Diagnostic]
    operations: Mapping[str, OperationSpec]
    analysis: CompileAnalysis
    protocol_analysis: ProtocolAnalysis
    enforce_binding: bool
    content_whitelist_mode: str
    content_type_policy: str


@dataclass
class HandlerState:
    stop: bool = False


@dataclass(frozen=True)
class ChildExpression:
    expr: Any
    node_id: str | None
    allow_source_partition: bool = False


@dataclass(frozen=True)
class ChildBlock:
    statements: list[IRStatement]
    defined_names: set[str] | None = None
    active_requirements: tuple[str, ...] | None = None


class BaseStatementHandler:
    def handle(self, stmt: IRStatement, ctx: StatementValidationContext) -> None:
        state = self.prepare(stmt, ctx)
        if state.stop:
            return

        self.validate_pre_binding_contracts(stmt, ctx, state)
        if state.stop:
            return

        self.validate_bindings(stmt, ctx, state)
        if state.stop:
            return

        self.validate_post_binding_contracts(stmt, ctx, state)
        if state.stop:
            return

        self.apply_state_before_children(stmt, ctx, state)
        if state.stop:
            return

        for child in self.iter_child_expressions(stmt, ctx, state):
            if child.allow_source_partition:
                self.validate_expr(
                    child.expr,
                    ctx,
                    node_id=child.node_id,
                    allow_source_partition=True,
                )
            else:
                self.validate_expr(child.expr, ctx, node_id=child.node_id)
        if state.stop:
            return

        for child_block in self.iter_child_blocks(stmt, ctx, state):
            self.recurse(
                child_block.statements,
                ctx,
                defined_names=child_block.defined_names,
                active_requirements=child_block.active_requirements,
            )
        if state.stop:
            return

        self.validate_post_child_contracts(stmt, ctx, state)
        if state.stop:
            return

        self.apply_state_after_children(stmt, ctx, state)

    def prepare(self, stmt: IRStatement, ctx: StatementValidationContext) -> HandlerState:
        del stmt, ctx
        return HandlerState()

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def validate_post_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def apply_state_before_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del stmt, ctx, state
        return ()

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del stmt, ctx, state
        return ()

    def validate_post_child_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def apply_state_after_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx, state

    def append_diagnostics(
        self,
        ctx: StatementValidationContext,
        diagnostics: list[Diagnostic],
    ) -> None:
        ctx.diagnostics.extend(diagnostics)

    def validate_expr(
        self,
        expr: Any,
        ctx: StatementValidationContext,
        *,
        node_id: str | None,
        allow_source_partition: bool = False,
    ) -> None:
        ctx.diagnostics.extend(
            validate_expr_contracts(
                expr,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                group_bindings=ctx.group_bindings,
                node_id=node_id,
                content_whitelist_mode=ctx.content_whitelist_mode,
                content_type_policy=ctx.content_type_policy,
                allow_source_partition=allow_source_partition,
            )
        )

    def copy_block_context(
        self,
        ctx: StatementValidationContext,
        *,
        defined_names: set[str] | None = None,
        active_requirements: tuple[str, ...] | None = None,
    ) -> StatementValidationContext:
        return StatementValidationContext(
            literal_bindings=dict(ctx.literal_bindings),
            expr_bindings=dict(ctx.expr_bindings),
            group_bindings=dict(ctx.group_bindings),
            defined_names=set(ctx.defined_names if defined_names is None else defined_names),
            active_requirements=ctx.active_requirements if active_requirements is None else active_requirements,
            diagnostics=ctx.diagnostics,
            operations=ctx.operations,
            analysis=ctx.analysis,
            protocol_analysis=ctx.protocol_analysis,
            enforce_binding=ctx.enforce_binding,
            content_whitelist_mode=ctx.content_whitelist_mode,
            content_type_policy=ctx.content_type_policy,
        )

    def recurse(
        self,
        statements: list[IRStatement],
        ctx: StatementValidationContext,
        *,
        defined_names: set[str] | None = None,
        active_requirements: tuple[str, ...] | None = None,
    ) -> None:
        validate_statement_list_with_context(
            statements,
            self.copy_block_context(
                ctx,
                defined_names=defined_names,
                active_requirements=active_requirements,
            ),
        )


@dataclass
class LetState(HandlerState):
    binding_diagnostics: list[Diagnostic] = field(default_factory=list)


class LetHandler(BaseStatementHandler):
    def prepare(self, stmt: IRStatement, ctx: StatementValidationContext) -> HandlerState:
        del stmt, ctx
        return LetState()

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        self.append_diagnostics(
            ctx,
            validate_active_constraint_compatibility(stmt, active_requirements=ctx.active_requirements),
        )
        if isinstance(stmt.value, IRCall):
            self.append_diagnostics(
                ctx,
                validate_let_call_contract(
                    stmt,
                    literal_bindings=ctx.literal_bindings,
                    expr_bindings=ctx.expr_bindings,
                    operations=ctx.operations,
                    content_whitelist_mode=ctx.content_whitelist_mode,
                    content_type_policy=ctx.content_type_policy,
                ),
            )

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        state = cast(LetState, state)
        if stmt.value is not None:
            state.binding_diagnostics = BindingValidator.validate_unbound_name_references_for_expr(
                expr=stmt.value,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
                span=stmt.span,
                node_id=stmt.id,
            )
            ctx.diagnostics.extend(state.binding_diagnostics)

    def apply_state_before_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRLet, stmt)
        if stmt.value is not None:
            ctx.expr_bindings[stmt.name] = stmt.value
        else:
            ctx.expr_bindings.pop(stmt.name, None)
        resolved = BindingValidator.resolve_let_value(stmt, ctx.literal_bindings)
        if resolved is not None:
            ctx.literal_bindings[stmt.name] = resolved
        else:
            ctx.literal_bindings.pop(stmt.name, None)
        binding = GroupIndexValidator.classify_binding(
            stmt.value,
            literal_bindings=ctx.literal_bindings,
            expr_bindings=ctx.expr_bindings,
        )
        if binding is not None:
            ctx.group_bindings[stmt.name] = binding
        else:
            ctx.group_bindings.pop(stmt.name, None)

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRLet, stmt)
        if stmt.value is not None:
            yield ChildExpression(stmt.value, stmt.id)

    def apply_state_after_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        state = cast(LetState, state)
        if not state.binding_diagnostics and BindingValidator.let_defines_runtime_name(
            stmt,
            expr_bindings=ctx.expr_bindings,
        ):
            ctx.defined_names.add(stmt.name)


class AssignHandler(BaseStatementHandler):
    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRAssign, stmt)
        self.append_diagnostics(
            ctx,
            validate_assign_target_contract(
                stmt,
                expr_bindings=ctx.expr_bindings,
                defined_names=ctx.defined_names,
            ),
        )

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRAssign, stmt)
        self.append_diagnostics(
            ctx,
            BindingValidator.validate_unbound_name_references_for_expr(
                expr=stmt.value,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
                span=stmt.span,
                node_id=stmt.id,
            ),
        )

    def apply_state_before_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRAssign, stmt)
        assign_root = BindingValidator.assign_target_root_name(stmt.target)
        if assign_root is not None and isinstance(stmt.target, IRIdentifier):
            ctx.expr_bindings[assign_root] = stmt.value
            ctx.literal_bindings.pop(assign_root, None)

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRAssign, stmt)
        yield ChildExpression(stmt.value, stmt.id)
        yield ChildExpression(stmt.target, stmt.id)


class IncludeHandler(BaseStatementHandler):
    def apply_state_before_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRInclude, stmt)
        target_id = ctx.protocol_analysis.include_targets.get(stmt.id)
        if target_id is not None:
            target_analysis = ctx.analysis.protocols.get(target_id)
            if target_analysis is not None:
                ctx.defined_names.update(target_analysis.runtime_exports)


class WithEnvHandler(BaseStatementHandler):
    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRWithEnv, stmt)
        self.append_diagnostics(
            ctx,
            validate_active_env_constraint_compatibility(
                stmt,
                expr_bindings=ctx.expr_bindings,
                active_requirements=ctx.active_requirements,
            ),
        )

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRWithEnv, stmt)
        self.append_diagnostics(
            ctx,
            BindingValidator.validate_unbound_name_references_for_with_env(
                stmt=stmt,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
            ),
        )

    def validate_post_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRWithEnv, stmt)
        self.append_diagnostics(
            ctx,
            EnvContractValidator.validate_with_env(
                stmt,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
            ),
        )

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRWithEnv, stmt)
        for arg in stmt.env_args:
            yield ChildExpression(arg.value, stmt.id)
        for target in stmt.targets:
            yield ChildExpression(target, stmt.id)

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del ctx, state
        stmt = cast(IRWithEnv, stmt)
        yield ChildBlock(stmt.statements)


@dataclass
class WithConstraintState(HandlerState):
    merged_requirements: tuple[str, ...] = ()


class WithConstraintHandler(BaseStatementHandler):
    def prepare(self, stmt: IRStatement, ctx: StatementValidationContext) -> HandlerState:
        stmt = cast(IRWithConstraint, stmt)
        return WithConstraintState(
            merged_requirements=tuple(
                dedupe_requirement_names(ctx.active_requirements + tuple(stmt.requirements))
            )
        )

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRWithConstraint, stmt)
        self.append_diagnostics(
            ctx,
            validate_with_constraint_contract(
                stmt,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
            ),
        )

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRWithConstraint, stmt)
        for arg in stmt.options:
            yield ChildExpression(arg.value, stmt.id)

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del ctx
        stmt = cast(IRWithConstraint, stmt)
        state = cast(WithConstraintState, state)
        yield ChildBlock(stmt.statements, active_requirements=state.merged_requirements)


class RepeatHandler(BaseStatementHandler):
    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRRepeat, stmt)
        self.append_diagnostics(
            ctx,
            BindingValidator.validate_unbound_name_references_for_expr(
                expr=stmt.iterable,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
                span=stmt.span,
                node_id=stmt.id,
            ),
        )

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRRepeat, stmt)
        yield ChildExpression(stmt.iterable, stmt.id)

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del state
        stmt = cast(IRRepeat, stmt)
        nested_defined_names = set(ctx.defined_names)
        nested_defined_names.add(stmt.binding)
        yield ChildBlock(stmt.statements, defined_names=nested_defined_names)


class ConditionalHandler(BaseStatementHandler):
    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRConditional, stmt)
        yield ChildExpression(stmt.condition, stmt.id)

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del ctx, state
        stmt = cast(IRConditional, stmt)
        yield ChildBlock(stmt.then_statements)
        yield ChildBlock(stmt.else_statements)


class ControlHandler(BaseStatementHandler):
    pass


class MutationHandler(BaseStatementHandler):
    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRMutation, stmt)
        self.append_diagnostics(
            ctx,
            validate_active_constraint_compatibility(stmt, active_requirements=ctx.active_requirements),
        )

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRMutation, stmt)
        self.append_diagnostics(
            ctx,
            BindingValidator.validate_unbound_name_references_for_mutation(
                stmt=stmt,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
            ),
        )

    def validate_post_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del state
        stmt = cast(IRMutation, stmt)
        self.append_diagnostics(
            ctx,
            validate_mutation_contract(
                stmt,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                group_bindings=ctx.group_bindings,
            ),
        )

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRMutation, stmt)
        if stmt.target is not None:
            yield ChildExpression(stmt.target, stmt.id)
        for source in stmt.sources:
            if isinstance(source, IRPair):
                yield ChildExpression(source.left, stmt.id, allow_source_partition=True)
                yield ChildExpression(source.right, stmt.id)
            else:
                yield ChildExpression(source, stmt.id, allow_source_partition=True)


@dataclass
class StepState(HandlerState):
    op_spec: OperationSpec | None = None
    builtin_method: bool = False


class StepHandler(BaseStatementHandler):
    def prepare(self, stmt: IRStatement, ctx: StatementValidationContext) -> HandlerState:
        stmt = cast(IRStep, stmt)
        if stmt.name in BUILTIN_METHOD_STEPS:
            return StepState(builtin_method=True)
        return StepState(op_spec=ctx.operations.get(stmt.name))

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        state = cast(StepState, state)
        self.append_diagnostics(
            ctx,
            validate_active_constraint_compatibility(stmt, active_requirements=ctx.active_requirements),
        )
        if state.builtin_method:
            return

        if state.op_spec is None:
            ctx.diagnostics.append(
                Diagnostic(
                    code="SEM_UNKNOWN_STEP",
                    message=f"Unknown step name: {stmt.name}",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
            state.stop = True
            return

        required_args = state.op_spec.required_args
        allowed_args = state.op_spec.allowed_args
        arg_names = [arg.name for arg in stmt.args]
        arg_name_set = set(arg_names)

        for missing in sorted(required_args - arg_name_set):
            if stmt.name == "DefineContent" and missing == "kind":
                ctx.diagnostics.append(
                    Diagnostic(
                        code="SEM_MISSING_CONTENT_KIND",
                        message="DefineContent requires arg 'kind'",
                        span=stmt.span,
                        node_id=stmt.id,
                    )
                )
                continue
            ctx.diagnostics.append(
                Diagnostic(
                    code="SEM_MISSING_REQUIRED_ARG",
                    message=f"Missing required arg '{missing}' in step '{stmt.name}'",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )

        for arg in stmt.args:
            if arg.name not in allowed_args:
                ctx.diagnostics.append(
                    Diagnostic(
                        code="SEM_UNKNOWN_ARG",
                        message=f"Unknown arg '{arg.name}' in step '{stmt.name}'",
                        span=arg.span,
                        node_id=stmt.id,
                    )
                )

        seen: set[str] = set()
        duplicates: list[str] = []
        for name in arg_names:
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)

        for dup in duplicates:
            dup_span = next((a.span for a in stmt.args if a.name == dup), stmt.span)
            ctx.diagnostics.append(
                Diagnostic(
                    code="SEM_DUPLICATE_ARG",
                    message=f"Duplicate arg '{dup}' in step '{stmt.name}'",
                    span=dup_span,
                    node_id=stmt.id,
                )
            )

        self.append_diagnostics(
            ctx,
            ConstructorValidator.validate_container_content_constructor_semantics(
                step=stmt,
                literal_bindings=ctx.literal_bindings,
                content_whitelist_mode=ctx.content_whitelist_mode,
                content_type_policy=ctx.content_type_policy,
            ),
        )
        self.append_diagnostics(
            ctx,
            validate_readout_schema_contract(
                stmt.name,
                stmt.args,
                literal_bindings=ctx.literal_bindings,
                node_id=stmt.id,
                span=stmt.span,
            ),
        )

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        state = cast(StepState, state)
        if state.builtin_method:
            return
        self.append_diagnostics(
            ctx,
            BindingValidator.validate_unbound_name_references_for_step(
                step=stmt,
                defined_names=ctx.defined_names,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
                strict_mode=ctx.enforce_binding,
            ),
        )

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del ctx, state
        stmt = cast(IRStep, stmt)
        for arg in stmt.args:
            yield ChildExpression(arg.value, stmt.id)

    def validate_post_child_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        state = cast(StepState, state)
        if state.builtin_method:
            return
        self.append_diagnostics(ctx, validate_agit_contract(stmt, literal_bindings=ctx.literal_bindings))

    def apply_state_after_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        state = cast(StepState, state)
        if state.builtin_method:
            return
        ctx.defined_names.update(
            defined_names_from_step(
                stmt=stmt,
                literal_bindings=ctx.literal_bindings,
                expr_bindings=ctx.expr_bindings,
            )
        )


_STATEMENT_HANDLERS_BY_TYPE: dict[type[object], BaseStatementHandler] = {
    IRLet: LetHandler(),
    IRAssign: AssignHandler(),
    IRInclude: IncludeHandler(),
    IRWithEnv: WithEnvHandler(),
    IRWithConstraint: WithConstraintHandler(),
    IRRepeat: RepeatHandler(),
    IRConditional: ConditionalHandler(),
    IRControl: ControlHandler(),
    IRMutation: MutationHandler(),
    IRStep: StepHandler(),
}


def validate_statement_list_with_context(
    statements: list[IRStatement],
    ctx: StatementValidationContext,
) -> None:
    for stmt in statements:
        handler = _STATEMENT_HANDLERS_BY_TYPE.get(type(stmt))
        if handler is not None:
            handler.handle(stmt, ctx)
