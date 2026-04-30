"""Statement lowering for AST -> IR compile."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from culsma.parser.ast_nodes import (
    AssignStatement,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStatement,
    Expression,
    Identifier,
    IfStatement,
    IncludeStatement,
    IndexExpr,
    LetStatement,
    MemberExpr,
    MethodCallExpr,
    MutationStmt,
    ProtocolRefStatement,
    RepeatStatement,
    ReturnStatement,
    Statement,
    StepCall,
    WithConstraintStmt,
    WithEnvStmt,
)
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRConditional,
    IRControl,
    IRInclude,
    IRLet,
    IRMutation,
    IRRepeat,
    IRStatement,
    IRStep,
    IRWithConstraint,
    IRWithEnv,
)

from .context import BlockContext, CompileSession, _require_span
from .expressions import ExprCompiler
from .callable import (
    _READOUT_FAMILY,
    CallableLowering,
)
from .targets import (
    _assignment_target_root_name,
    _contains_invalid_hold_statement,
    _extract_explicit_hold_target,
    _is_explicit_hold_only_block,
    TargetResolver,
)
from .schedule import (
    ScheduleEvaluator,
    _extract_env_time_boundary,
    _resolve_let_bound_expr,
    _supports_runtime_boolean_surface,
)

_FORBIDDEN_SOURCE_STEP_CALLS = {"LoadContent", "AnnotateContent"}
_FORBIDDEN_LEGACY_SOURCE_CALLS = {
    "Transfer",
    "Mix",
    "Dilute",
    "Discard",
    "Resuspend",
    "Centrifuge",
    "MagneticSeparate",
    "htr",
    "htr_program",
    "flow_program",
    "seq_program",
    "ms_program",
}


@dataclass
class StatementLoweringContext:
    stmt_id: str
    stmt_index: int
    block_context: BlockContext
    statement_compiler: StatementCompiler
    session: CompileSession
    expr_compiler: ExprCompiler
    callable_lowering: CallableLowering
    target_resolver: TargetResolver
    schedule_evaluator: ScheduleEvaluator

    @property
    def ctx(self) -> BlockContext:
        return self.block_context


@dataclass
class StatementLoweringState:
    output: list[IRStatement] | None = None


class BaseStatementCompileHandler:
    def handle(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> list[IRStatement]:
        state = self.prepare(stmt, lowering_ctx)
        if state.output is not None:
            return state.output

        self.resolve_source_form(stmt, lowering_ctx, state)
        if state.output is not None:
            return state.output

        self.validate_source_shape(stmt, lowering_ctx, state)
        if state.output is not None:
            return state.output

        self.apply_state_before_lowering(stmt, lowering_ctx, state)
        prefix = self.lower_prefix_ir(stmt, lowering_ctx, state)
        current = self.lower_current_or_children(stmt, lowering_ctx, state)
        output = [*prefix, *current]
        self.apply_state_after_lowering(stmt, lowering_ctx, state, output)
        return state.output if state.output is not None else output

    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        _require_span(stmt, f"{lowering_ctx.ctx.scope_id}.statement[{lowering_ctx.stmt_index}]")
        return StatementLoweringState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx, state

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx, state

    def apply_state_before_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx, state

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del stmt, lowering_ctx, state
        return []

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del stmt, lowering_ctx, state
        return []

    def apply_state_after_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
        output: list[IRStatement],
    ) -> None:
        del stmt, lowering_ctx, state, output


class StatementCompiler:
    def __init__(
        self,
        *,
        session: CompileSession,
        expr_compiler: ExprCompiler,
        callable_lowering: CallableLowering,
        target_resolver: TargetResolver,
        schedule_evaluator: ScheduleEvaluator,
    ) -> None:
        self.session = session
        self.expr_compiler = expr_compiler
        self.callable_lowering = callable_lowering
        self.target_resolver = target_resolver
        self.schedule_evaluator = schedule_evaluator

    def compile_list(self, statements: list[Statement], *, ctx: BlockContext) -> list[IRStatement]:
        compiled_statements: list[IRStatement] = []
        next_index = 0
        protocol_id = ctx.scope_id.split(".", maxsplit=1)[0]
        for stmt in statements:
            compiled = self.compile(stmt, ctx=ctx, stmt_index=next_index)
            self.session.analysis_builder.record_statement_effects(
                protocol_id=protocol_id,
                statements=compiled,
                protocols_by_name=self.session.protocol_id_by_name,
                collect_runtime_exports=ctx.scope_id == protocol_id,
                expr_bindings=ctx.ir_expr_bindings,
                env=ctx.ir_const_env,
            )
            compiled_statements.extend(compiled)
            next_index += len(compiled)
        return compiled_statements

    def compile(self, stmt: Statement, *, ctx: BlockContext, stmt_index: int) -> list[IRStatement]:
        stmt_id = f"{ctx.scope_id}.s{stmt_index}"
        lowering_ctx = StatementLoweringContext(
            stmt_id=stmt_id,
            stmt_index=stmt_index,
            block_context=ctx,
            statement_compiler=self,
            session=self.session,
            expr_compiler=self.expr_compiler,
            callable_lowering=self.callable_lowering,
            target_resolver=self.target_resolver,
            schedule_evaluator=self.schedule_evaluator,
        )
        handler = _STATEMENT_HANDLERS_BY_TYPE.get(type(stmt))
        if handler is not None:
            return handler.handle(stmt, lowering_ctx)
        _require_span(stmt, f"{ctx.scope_id}.statement[{stmt_index}]")
        raise TypeError(f"Unsupported statement type: {type(stmt).__name__}")


@dataclass
class ProtocolRefState(StatementLoweringState):
    resolved_name: str = ""


class IncludeHandler(BaseStatementCompileHandler):
    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        stmt = cast(IncludeStatement, stmt)
        return [
            IRInclude(
                id=lowering_ctx.stmt_id,
                name=stmt.name,
                args=[],
                span=stmt.span,
            )
        ]


class ProtocolRefHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return ProtocolRefState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(ProtocolRefStatement, stmt)
        state = cast(ProtocolRefState, state)
        qualified_name = f"{stmt.module}.{stmt.protocol}"
        state.resolved_name = lowering_ctx.session.qualified_protocol_lookup.get(qualified_name, qualified_name)

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(ProtocolRefStatement, stmt)
        state = cast(ProtocolRefState, state)
        return [
            IRInclude(
                id=lowering_ctx.stmt_id,
                name=state.resolved_name,
                args=[lowering_ctx.expr_compiler.compile_arg(arg) for arg in stmt.args],
                span=stmt.span,
            )
        ]


@dataclass
class LetState(StatementLoweringState):
    readout_prefix: list[IRLet] = field(default_factory=list)
    normalized_value: Expression | None = None


class LetHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return LetState()

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del lowering_ctx, state
        stmt = cast(LetStatement, stmt)
        if isinstance(stmt.value, CallExpr) and stmt.value.name in _FORBIDDEN_SOURCE_STEP_CALLS:
            raise ValueError(f"{stmt.value.name}(...) is internal-only and cannot be called directly from source")
        if isinstance(stmt.value, CallExpr) and stmt.value.name in _FORBIDDEN_LEGACY_SOURCE_CALLS:
            raise ValueError(f"{stmt.value.name}(...) is legacy-only and cannot be called directly from current source")

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(LetStatement, stmt)
        state = cast(LetState, state)
        if isinstance(stmt.value, CallExpr) and stmt.value.name in _READOUT_FAMILY:
            readout_prefix, normalized_value = lowering_ctx.callable_lowering.normalize_grouped_readout_call(
                stmt.value,
                stmt_id=lowering_ctx.stmt_id,
                ctx=lowering_ctx.ctx,
            )
            state.readout_prefix = readout_prefix
            state.normalized_value = normalized_value

    def apply_state_before_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(LetStatement, stmt)
        state = cast(LetState, state)
        ctx = lowering_ctx.ctx
        ctx.local_names.add(stmt.name)
        if state.normalized_value is not None:
            ctx.let_bindings[stmt.name] = state.normalized_value
            return

        numeric_value = lowering_ctx.schedule_evaluator.try_eval_numeric_expr(stmt.value, ctx=ctx)
        bool_value = lowering_ctx.schedule_evaluator.try_eval_bool_expr(stmt.value, ctx=ctx)
        if numeric_value is not None:
            ctx.const_env[stmt.name] = numeric_value
        elif bool_value is not None:
            ctx.const_env[stmt.name] = bool_value
        else:
            ctx.const_env.pop(stmt.name, None)
        if stmt.value is not None:
            ctx.let_bindings[stmt.name] = stmt.value
        else:
            ctx.let_bindings.pop(stmt.name, None)

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del stmt, lowering_ctx
        state = cast(LetState, state)
        return list(state.readout_prefix)

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(LetStatement, stmt)
        state = cast(LetState, state)
        value = state.normalized_value if state.normalized_value is not None else stmt.value
        return [
            IRLet(
                id=lowering_ctx.stmt_id,
                name=stmt.name,
                value=lowering_ctx.expr_compiler.compile(value),
                span=stmt.span,
            )
        ]


@dataclass
class AssignState(StatementLoweringState):
    target_root: str | None = None


class AssignHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return AssignState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del lowering_ctx
        stmt = cast(AssignStatement, stmt)
        state = cast(AssignState, state)
        state.target_root = _assignment_target_root_name(stmt.target)

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt
        state = cast(AssignState, state)
        if state.target_root is None:
            raise ValueError("assignment target must be a local name or member path rooted at a local name")
        if state.target_root not in lowering_ctx.ctx.local_names:
            raise ValueError(f"assignment target '{state.target_root}' must be previously declared")

    def apply_state_before_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(AssignStatement, stmt)
        state = cast(AssignState, state)
        ctx = lowering_ctx.ctx
        target_root = state.target_root
        if target_root is not None and isinstance(stmt.target, Identifier):
            numeric_value = lowering_ctx.schedule_evaluator.try_eval_numeric_expr(stmt.value, ctx=ctx)
            bool_value = lowering_ctx.schedule_evaluator.try_eval_bool_expr(stmt.value, ctx=ctx)
            if numeric_value is not None:
                ctx.const_env[target_root] = numeric_value
            elif bool_value is not None:
                ctx.const_env[target_root] = bool_value
            else:
                ctx.const_env.pop(target_root, None)
            ctx.let_bindings[target_root] = stmt.value

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        stmt = cast(AssignStatement, stmt)
        return [
            IRAssign(
                id=lowering_ctx.stmt_id,
                target=lowering_ctx.expr_compiler.compile(stmt.target),
                value=lowering_ctx.expr_compiler.compile(stmt.value),
                span=stmt.span,
            )
        ]


class ExprStatementHandler(BaseStatementCompileHandler):
    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del lowering_ctx, state
        stmt = cast(ExprStatement, stmt)
        if not isinstance(stmt.value, MethodCallExpr):
            raise ValueError(f"Unsupported expression statement type: {type(stmt.value).__name__}")

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        stmt = cast(ExprStatement, stmt)
        value = cast(MethodCallExpr, stmt.value)
        return [
            IRStep(
                id=lowering_ctx.stmt_id,
                name=value.method,
                args=lowering_ctx.expr_compiler.compile_method_call_step_args(value),
                span=stmt.span,
            )
        ]


class ReturnHandler(BaseStatementCompileHandler):
    pass


@dataclass
class WithEnvState(StatementLoweringState):
    explicit_hold: bool = False
    nested_statements: list[Statement] = field(default_factory=list)
    target_prefix: list[IRLet] = field(default_factory=list)
    flattened_targets: list[Expression] = field(default_factory=list)
    nested_env_time_boundary: Quantity | None = None


class WithEnvHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return WithEnvState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(WithEnvStmt, stmt)
        state = cast(WithEnvState, state)
        ctx = lowering_ctx.ctx
        if not stmt.statements:
            state.explicit_hold = False
            state.nested_statements = []
            state.target_prefix = []
            state.flattened_targets = []
        else:
            state.explicit_hold = _is_explicit_hold_only_block(stmt.statements)
        if stmt.statements and state.explicit_hold:
            hold_target = _extract_explicit_hold_target(stmt.statements[0], let_bindings=ctx.let_bindings)
            state.nested_statements = []
            state.target_prefix, state.flattened_targets = lowering_ctx.target_resolver.expand_env_targets(
                [hold_target],
                stmt_id=lowering_ctx.stmt_id,
                ctx=ctx,
            )
        elif stmt.statements:
            state.nested_statements = stmt.statements
            if not _contains_invalid_hold_statement(stmt.statements):
                state.target_prefix, state.flattened_targets = (
                    lowering_ctx.target_resolver.infer_env_targets_from_source_statements(
                        stmt.statements,
                        stmt_id=lowering_ctx.stmt_id,
                        ctx=ctx,
                    )
                )
        state.nested_env_time_boundary = _extract_env_time_boundary(stmt, ctx.let_bindings)

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del lowering_ctx
        stmt = cast(WithEnvStmt, stmt)
        state = cast(WithEnvState, state)
        if stmt.statements and not state.explicit_hold and _contains_invalid_hold_statement(stmt.statements):
            raise ValueError("hold(sample = ...) must be the only statement inside with env(...)")
        if stmt.statements and not state.explicit_hold and not state.flattened_targets:
            raise ValueError("with env(...): could not infer env target from body; use hold(sample = ...) for pure env hold")

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del stmt, lowering_ctx
        state = cast(WithEnvState, state)
        return list(state.target_prefix)

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(WithEnvStmt, stmt)
        state = cast(WithEnvState, state)
        ctx = lowering_ctx.ctx
        return [
            IRWithEnv(
                id=lowering_ctx.stmt_id,
                env_args=[lowering_ctx.expr_compiler.compile_arg(arg) for arg in stmt.env_args],
                targets=[lowering_ctx.expr_compiler.compile(target) for target in state.flattened_targets],
                statements=lowering_ctx.statement_compiler.compile_list(
                    state.nested_statements,
                    ctx=ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.b",
                        const_env=ctx.const_env,
                        let_bindings=dict(ctx.let_bindings),
                        local_names=set(ctx.local_names),
                        env_time_boundary=state.nested_env_time_boundary,
                    ),
                ),
                explicit_hold=state.explicit_hold,
                span=stmt.span,
            )
        ]


class WithConstraintHandler(BaseStatementCompileHandler):
    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        stmt = cast(WithConstraintStmt, stmt)
        ctx = lowering_ctx.ctx
        return [
            IRWithConstraint(
                id=lowering_ctx.stmt_id,
                requirements=list(stmt.requirements),
                options=[lowering_ctx.expr_compiler.compile_arg(arg) for arg in stmt.options],
                statements=lowering_ctx.statement_compiler.compile_list(
                    stmt.statements,
                    ctx=ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.b",
                        const_env=ctx.const_env,
                        let_bindings=dict(ctx.let_bindings),
                        local_names=set(ctx.local_names),
                    ),
                ),
                span=stmt.span,
            )
        ]


@dataclass
class MutationState(StatementLoweringState):
    target_prefix: list[IRLet] = field(default_factory=list)
    flattened_targets: list[Expression] = field(default_factory=list)
    expanded_sources: list[list[Expression]] = field(default_factory=list)


class MutationHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return MutationState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(MutationStmt, stmt)
        state = cast(MutationState, state)
        state.target_prefix, state.flattened_targets = lowering_ctx.target_resolver.expand_mutation_targets(
            stmt.target,
            stmt_id=lowering_ctx.stmt_id,
            ctx=lowering_ctx.ctx,
        )
        state.expanded_sources = lowering_ctx.target_resolver.expand_mutation_sources(
            stmt.sources,
            target=stmt.target,
            flattened_targets=state.flattened_targets,
            ctx=lowering_ctx.ctx,
        )

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del stmt, lowering_ctx
        state = cast(MutationState, state)
        return list(state.target_prefix)

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(MutationStmt, stmt)
        state = cast(MutationState, state)
        return [
            IRMutation(
                id=f"{lowering_ctx.stmt_id}.g{idx}" if len(state.flattened_targets) > 1 else lowering_ctx.stmt_id,
                target=lowering_ctx.expr_compiler.compile(target),
                sources=[lowering_ctx.expr_compiler.compile(source) for source in state.expanded_sources[idx]],
                span=stmt.span,
            )
            for idx, target in enumerate(state.flattened_targets)
        ]


@dataclass
class StepCallState(StatementLoweringState):
    readout_prefix: list[IRLet] = field(default_factory=list)
    normalized_step: StepCall | None = None
    lowered_name: str | None = None
    lowered_args: list = field(default_factory=list)


class StepCallHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return StepCallState()

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del lowering_ctx, state
        stmt = cast(StepCall, stmt)
        if stmt.name in _FORBIDDEN_SOURCE_STEP_CALLS:
            raise ValueError(f"{stmt.name}(...) is internal-only and cannot be called directly from source")
        if stmt.name in _FORBIDDEN_LEGACY_SOURCE_CALLS:
            raise ValueError(f"{stmt.name}(...) is legacy-only and cannot be called directly from current source")
        if stmt.name == "hold":
            raise ValueError("hold(sample = ...) is only valid as the sole statement inside with env(...)")

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(StepCall, stmt)
        state = cast(StepCallState, state)
        if stmt.name in _READOUT_FAMILY:
            readout_prefix, normalized_step = lowering_ctx.callable_lowering.normalize_grouped_readout_stepcall(
                stmt,
                stmt_id=lowering_ctx.stmt_id,
                ctx=lowering_ctx.ctx,
            )
            state.readout_prefix = readout_prefix
            state.normalized_step = normalized_step
        return list(state.readout_prefix)

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(StepCall, stmt)
        state = cast(StepCallState, state)
        step = state.normalized_step if state.normalized_step is not None else stmt
        lowered_name, lowered_args = lowering_ctx.callable_lowering.lower_callable(
            step.name,
            step.args,
            step.span,
        )
        return [
            IRStep(
                id=lowering_ctx.stmt_id,
                name=lowered_name,
                args=[lowering_ctx.expr_compiler.compile_arg(arg) for arg in lowered_args],
                span=step.span,
            )
        ]


class ControlHandler(BaseStatementCompileHandler):
    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        return [
            IRControl(
                id=lowering_ctx.stmt_id,
                action="break" if isinstance(stmt, BreakStmt) else "continue",
                span=stmt.span,
            )
        ]


class RepeatHandler(BaseStatementCompileHandler):
    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        del state
        stmt = cast(RepeatStatement, stmt)
        if stmt.binding is not None:
            return self._lower_binding_repeat(stmt, lowering_ctx)
        return self._lower_count_repeat(stmt, lowering_ctx)

    def apply_state_after_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
        output: list[IRStatement],
    ) -> None:
        del state, output
        stmt = cast(RepeatStatement, stmt)
        lowering_ctx.schedule_evaluator.invalidate_runtime_mutated_names(stmt.statements, ctx=lowering_ctx.ctx)

    def _lower_binding_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        iterable_values = lowering_ctx.schedule_evaluator.resolve_repeat_iterable_values(
            stmt.iterable,
            ctx=lowering_ctx.ctx,
        )
        if iterable_values is not None:
            return self._lower_iterable_values(stmt, lowering_ctx, iterable_values)

        resolved_iterable = _resolve_let_bound_expr(stmt.iterable, lowering_ctx.ctx.let_bindings)
        runtime_iterable_surface = isinstance(
            resolved_iterable,
            (Identifier, CallExpr, MemberExpr, IndexExpr),
        )
        if runtime_iterable_surface and not (
            isinstance(resolved_iterable, CallExpr) and resolved_iterable.name == "schedule"
        ):
            compiled_body = lowering_ctx.statement_compiler.compile_list(
                stmt.statements,
                ctx=lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.b",
                    const_env=lowering_ctx.ctx.const_env,
                    let_bindings=dict(lowering_ctx.ctx.let_bindings),
                    local_names=set(lowering_ctx.ctx.local_names) | {stmt.binding},
                ),
            )
            return [
                IRRepeat(
                    id=lowering_ctx.stmt_id,
                    binding=stmt.binding,
                    iterable=lowering_ctx.expr_compiler.compile(stmt.iterable),
                    statements=compiled_body,
                    span=stmt.span,
                )
            ]

        schedule_mode = lowering_ctx.schedule_evaluator.resolve_schedule_mode(stmt.iterable, ctx=lowering_ctx.ctx)
        if schedule_mode == "continuous":
            return self._lower_continuous_schedule(stmt, lowering_ctx)
        points = lowering_ctx.schedule_evaluator.eval_schedule_points(stmt.iterable, ctx=lowering_ctx.ctx)
        return self._lower_iterable_values(stmt, lowering_ctx, points)

    def _lower_iterable_values(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
        iterable_values: list[Expression],
    ) -> list[IRStatement]:
        expanded: list[IRStatement] = []
        loop_const_env = dict(lowering_ctx.ctx.const_env)
        loop_let_bindings = dict(lowering_ctx.ctx.let_bindings)
        loop_local_names = set(lowering_ctx.ctx.local_names)
        for iteration_index, point in enumerate(iterable_values):
            substituted_statements = [
                lowering_ctx.schedule_evaluator.substitute_statement(nested_stmt, stmt.binding, point)
                for nested_stmt in stmt.statements
            ]
            nested_const_env = dict(loop_const_env)
            nested_let_bindings = dict(loop_let_bindings)
            nested_local_names = set(loop_local_names)
            nested_let_bindings[stmt.binding] = point
            runtime_control = any(
                lowering_ctx.schedule_evaluator.statement_requires_runtime_control(
                    nested_stmt,
                    ctx=lowering_ctx.ctx.derive(const_env=nested_const_env),
                )
                for nested_stmt in substituted_statements
            )
            nested_stmt_index = 0
            stop_all_iterations = False
            for nested_stmt in substituted_statements:
                nested_ctx = lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.i{iteration_index}" if runtime_control else lowering_ctx.ctx.scope_id,
                    const_env=nested_const_env,
                    let_bindings=nested_let_bindings,
                    local_names=nested_local_names | {stmt.binding},
                )
                compiled_nested = lowering_ctx.statement_compiler.compile(
                    nested_stmt,
                    ctx=nested_ctx,
                    stmt_index=nested_stmt_index if runtime_control else lowering_ctx.stmt_index + len(expanded),
                )
                expanded.extend(compiled_nested)
                nested_stmt_index += len(compiled_nested)
                if not runtime_control:
                    control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                    if control_action == "continue":
                        break
                    if control_action == "break":
                        stop_all_iterations = True
                        break
            nested_let_bindings.pop(stmt.binding, None)
            nested_const_env.pop(stmt.binding, None)
            loop_const_env = nested_const_env
            loop_let_bindings = nested_let_bindings
            loop_local_names = nested_local_names
            if stop_all_iterations:
                break
        return expanded

    def _lower_continuous_schedule(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        window_boundary = lowering_ctx.schedule_evaluator.eval_continuous_schedule_boundary(
            stmt.iterable,
            ctx=lowering_ctx.ctx,
        )
        substituted_statements = list(stmt.statements)
        nested_const_env = dict(lowering_ctx.ctx.const_env)
        nested_let_bindings = dict(lowering_ctx.ctx.let_bindings)
        nested_local_names = set(lowering_ctx.ctx.local_names)
        runtime_control = any(
            lowering_ctx.schedule_evaluator.statement_requires_runtime_control(
                nested_stmt,
                ctx=lowering_ctx.ctx.derive(const_env=nested_const_env),
            )
            for nested_stmt in substituted_statements
        )
        expanded: list[IRStatement] = []
        nested_stmt_index = 0
        for nested_stmt in substituted_statements:
            compiled_nested = lowering_ctx.statement_compiler.compile(
                nested_stmt,
                ctx=lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.i0",
                    const_env=nested_const_env,
                    let_bindings=nested_let_bindings,
                    local_names=nested_local_names,
                    env_time_boundary=window_boundary,
                ),
                stmt_index=nested_stmt_index,
            )
            expanded.extend(compiled_nested)
            nested_stmt_index += len(compiled_nested)
            if not runtime_control:
                control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                if control_action in {"continue", "break"}:
                    break
        return expanded

    def _lower_count_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        iterations = lowering_ctx.schedule_evaluator.eval_repeat_count(stmt.times, ctx=lowering_ctx.ctx)
        expanded: list[IRStatement] = []
        runtime_control = any(
            lowering_ctx.schedule_evaluator.statement_requires_runtime_control(nested_stmt, ctx=lowering_ctx.ctx)
            for nested_stmt in stmt.statements
        )
        for iteration_index in range(iterations):
            nested_stmt_index = 0
            stop_all_iterations = False
            for nested_stmt in stmt.statements:
                compiled_nested = lowering_ctx.statement_compiler.compile(
                    nested_stmt,
                    ctx=lowering_ctx.ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.i{iteration_index}" if runtime_control else lowering_ctx.ctx.scope_id,
                    ),
                    stmt_index=nested_stmt_index if runtime_control else lowering_ctx.stmt_index + len(expanded),
                )
                expanded.extend(compiled_nested)
                nested_stmt_index += len(compiled_nested)
                if not runtime_control:
                    control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                    if control_action == "continue":
                        break
                    if control_action == "break":
                        stop_all_iterations = True
                        break
            if stop_all_iterations:
                break
        return expanded


@dataclass
class IfState(StatementLoweringState):
    condition: bool | None = None
    runtime_conditional: bool = False


class IfHandler(BaseStatementCompileHandler):
    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        super().prepare(stmt, lowering_ctx)
        return IfState()

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(IfStatement, stmt)
        state = cast(IfState, state)
        state.condition = lowering_ctx.schedule_evaluator.try_eval_bool_expr(stmt.condition, ctx=lowering_ctx.ctx)

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        stmt = cast(IfStatement, stmt)
        state = cast(IfState, state)
        if state.condition is not None:
            return
        if not _supports_runtime_boolean_surface(stmt.condition):
            raise ValueError("if condition must be a compile-time boolean expression or supported runtime predicate")
        state.runtime_conditional = True

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> list[IRStatement]:
        stmt = cast(IfStatement, stmt)
        state = cast(IfState, state)
        if state.condition is not None:
            selected = stmt.then_statements if state.condition else stmt.else_statements
            expanded: list[IRStatement] = []
            next_nested_index = 0
            for nested_stmt in selected:
                compiled_nested = lowering_ctx.statement_compiler.compile(
                    nested_stmt,
                    ctx=lowering_ctx.ctx,
                    stmt_index=lowering_ctx.stmt_index + next_nested_index,
                )
                expanded.extend(compiled_nested)
                next_nested_index += len(compiled_nested)
            return expanded

        return [
            IRConditional(
                id=lowering_ctx.stmt_id,
                condition=lowering_ctx.expr_compiler.compile(stmt.condition),
                then_statements=lowering_ctx.statement_compiler.compile_list(
                    stmt.then_statements,
                    ctx=lowering_ctx.ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.then",
                        const_env=dict(lowering_ctx.ctx.const_env),
                        let_bindings=dict(lowering_ctx.ctx.let_bindings),
                        local_names=set(lowering_ctx.ctx.local_names),
                    ),
                ),
                else_statements=lowering_ctx.statement_compiler.compile_list(
                    stmt.else_statements,
                    ctx=lowering_ctx.ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.else",
                        const_env=dict(lowering_ctx.ctx.const_env),
                        let_bindings=dict(lowering_ctx.ctx.let_bindings),
                        local_names=set(lowering_ctx.ctx.local_names),
                    ),
                ),
                span=stmt.span,
            )
        ]

    def apply_state_after_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
        output: list[IRStatement],
    ) -> None:
        del output
        stmt = cast(IfStatement, stmt)
        state = cast(IfState, state)
        if state.runtime_conditional:
            lowering_ctx.schedule_evaluator.invalidate_runtime_mutated_names(
                [*stmt.then_statements, *stmt.else_statements],
                ctx=lowering_ctx.ctx,
            )


_STATEMENT_HANDLERS_BY_TYPE: dict[type[object], BaseStatementCompileHandler] = {
    IncludeStatement: IncludeHandler(),
    ProtocolRefStatement: ProtocolRefHandler(),
    LetStatement: LetHandler(),
    AssignStatement: AssignHandler(),
    ExprStatement: ExprStatementHandler(),
    ReturnStatement: ReturnHandler(),
    WithEnvStmt: WithEnvHandler(),
    WithConstraintStmt: WithConstraintHandler(),
    MutationStmt: MutationHandler(),
    StepCall: StepCallHandler(),
    BreakStmt: ControlHandler(),
    ContinueStmt: ControlHandler(),
    RepeatStatement: RepeatHandler(),
    IfStatement: IfHandler(),
}
