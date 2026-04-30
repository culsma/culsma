"""Statement-level type and unit checking dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, cast

from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRCall,
    IRIdentifier,
    IRLet,
    IRMutation,
    IRRepeat,
    IRStatement,
    IRStep,
    IRWithConstraint,
    IRWithEnv,
)

from .context import TypecheckContext
from .expressions import DEFAULT_TYPECHECK_EXPRESSION_SERVICES, TypecheckExpressionServices


@dataclass
class TypecheckStatementState:
    stop: bool = False


@dataclass(frozen=True)
class ChildStatementBlock:
    statements: list[IRStatement]
    expr_bindings: dict[str, Any]


class BaseTypecheckStatementHandler:
    services: TypecheckExpressionServices = DEFAULT_TYPECHECK_EXPRESSION_SERVICES

    def handle(self, stmt: IRStatement, ctx: TypecheckContext) -> None:
        state = self.prepare(stmt, ctx)
        if state.stop:
            return

        self.validate_pre_binding_contracts(stmt, ctx, state)
        if state.stop:
            return

        self.update_or_derive_bindings(stmt, ctx, state)
        if state.stop:
            return

        self.check_child_expressions(stmt, ctx, state)
        if state.stop:
            return

        self.check_statement_specific_rules(stmt, ctx, state)
        if state.stop:
            return

        for child in self.iter_child_blocks(stmt, ctx, state):
            self.recurse(child, ctx)
        if state.stop:
            return

        self.apply_post_child_effects(stmt, ctx, state)

    def prepare(self, _stmt: IRStatement, _ctx: TypecheckContext) -> TypecheckStatementState:
        return TypecheckStatementState()

    def validate_pre_binding_contracts(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        return

    def update_or_derive_bindings(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        return

    def check_child_expressions(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        return

    def check_statement_specific_rules(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        return

    def iter_child_blocks(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> Iterable[ChildStatementBlock]:
        return ()

    def apply_post_child_effects(
        self,
        _stmt: IRStatement,
        _ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        return

    def recurse(self, child: ChildStatementBlock, ctx: TypecheckContext) -> None:
        if ctx.statement_typechecker is None:
            return
        child_ctx = ctx.derive_with_bindings(child.expr_bindings)
        ctx.statement_typechecker.typecheck_list(child.statements, child_ctx)


class LetTypecheckHandler(BaseTypecheckStatementHandler):
    def update_or_derive_bindings(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        if stmt.value is None:
            ctx.expr_bindings.pop(stmt.name, None)
            return
        ctx.expr_bindings[stmt.name] = stmt.value

    def check_child_expressions(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        if stmt.value is None:
            return
        ctx.extend(
            self.services.typecheck_program_calls_in_expr(
                stmt.value,
                node_id=stmt.id,
                expr_bindings=ctx.expr_bindings,
            )
        )
        if isinstance(stmt.value, IRCall):
            ctx.extend(
                self.services.typecheck_let_call(
                    stmt.name,
                    stmt.value,
                    stmt.id,
                    expr_bindings=ctx.expr_bindings,
                )
            )


class AssignTypecheckHandler(BaseTypecheckStatementHandler):
    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRAssign, stmt)
        ctx.extend(self.services.typecheck_assignment(stmt, expr_bindings=ctx.expr_bindings))

    def check_child_expressions(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRAssign, stmt)
        ctx.extend(
            self.services.typecheck_program_calls_in_expr(
                stmt.value,
                node_id=stmt.id,
                expr_bindings=ctx.expr_bindings,
            )
        )


class WithEnvTypecheckHandler(BaseTypecheckStatementHandler):
    def check_statement_specific_rules(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRWithEnv, stmt)
        ctx.extend(self.services.typecheck_with_env(stmt, expr_bindings=ctx.expr_bindings))

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> Iterable[ChildStatementBlock]:
        stmt = cast(IRWithEnv, stmt)
        return (ChildStatementBlock(stmt.statements, dict(ctx.expr_bindings)),)


class WithConstraintTypecheckHandler(BaseTypecheckStatementHandler):
    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> Iterable[ChildStatementBlock]:
        stmt = cast(IRWithConstraint, stmt)
        return (ChildStatementBlock(stmt.statements, dict(ctx.expr_bindings)),)


class RepeatTypecheckHandler(BaseTypecheckStatementHandler):
    def check_child_expressions(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRRepeat, stmt)
        ctx.extend(
            self.services.typecheck_program_calls_in_expr(
                stmt.iterable,
                node_id=stmt.id,
                expr_bindings=ctx.expr_bindings,
            )
        )

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> Iterable[ChildStatementBlock]:
        stmt = cast(IRRepeat, stmt)
        nested_bindings = dict(ctx.expr_bindings)
        nested_bindings[stmt.binding] = IRIdentifier(name=stmt.binding, span=stmt.span)
        return (ChildStatementBlock(stmt.statements, nested_bindings),)


class MutationTypecheckHandler(BaseTypecheckStatementHandler):
    def check_statement_specific_rules(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRMutation, stmt)
        ctx.extend(self.services.typecheck_mutation(stmt, expr_bindings=ctx.expr_bindings))


@dataclass
class StepTypecheckState(TypecheckStatementState):
    op_arg_dimensions: Mapping[str, frozenset[str]] | None = None


class StepTypecheckHandler(BaseTypecheckStatementHandler):
    def prepare(self, stmt: IRStatement, ctx: TypecheckContext) -> TypecheckStatementState:
        stmt = cast(IRStep, stmt)
        op_spec = ctx.operation_specs.get(stmt.name)
        if op_spec is None:
            return StepTypecheckState(stop=True)
        return StepTypecheckState(op_arg_dimensions=op_spec.arg_dimensions)

    def check_child_expressions(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        state = cast(StepTypecheckState, state)
        arg_dims = state.op_arg_dimensions or {}
        for arg in stmt.args:
            ctx.extend(
                self.services.typecheck_program_calls_in_expr(
                    arg.value,
                    node_id=stmt.id,
                    expr_bindings=ctx.expr_bindings,
                )
            )
            expected = arg_dims.get(arg.name)
            if not expected:
                continue
            if isinstance(arg.value, IRIdentifier):
                continue
            ctx.extend(
                self.services.validate_quantity_dimensions(
                    arg.value,
                    expected=list(expected),
                    non_quantity_code="TYPE_UNIT_NOT_ALLOWED",
                    mismatch_code="TYPE_DIMENSION_MISMATCH",
                    unknown_code="TYPE_UNKNOWN_UNIT",
                    label=f"Arg '{arg.name}' in step '{stmt.name}'",
                    span=arg.span or stmt.span,
                    node_id=stmt.id,
                )
            )

    def check_statement_specific_rules(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        _state: TypecheckStatementState,
    ) -> None:
        stmt = cast(IRStep, stmt)
        ctx.extend(self.services.typecheck_content_descriptors(stmt))


_STATEMENT_HANDLERS_BY_TYPE: dict[type[object], BaseTypecheckStatementHandler] = {
    IRLet: LetTypecheckHandler(),
    IRAssign: AssignTypecheckHandler(),
    IRWithEnv: WithEnvTypecheckHandler(),
    IRWithConstraint: WithConstraintTypecheckHandler(),
    IRRepeat: RepeatTypecheckHandler(),
    IRMutation: MutationTypecheckHandler(),
    IRStep: StepTypecheckHandler(),
}


class StatementTypechecker:
    def __init__(
        self,
        handlers_by_type: Mapping[type[object], BaseTypecheckStatementHandler] | None = None,
    ) -> None:
        self.handlers_by_type = dict(handlers_by_type or _STATEMENT_HANDLERS_BY_TYPE)

    def typecheck_list(self, statements: list[IRStatement], ctx: TypecheckContext) -> None:
        for stmt in statements:
            self.typecheck_statement(stmt, ctx)

    def typecheck_statement(self, stmt: IRStatement, ctx: TypecheckContext) -> None:
        handler = self.handlers_by_type.get(type(stmt))
        if handler is not None:
            previous_typechecker = ctx.statement_typechecker
            ctx.statement_typechecker = self
            try:
                handler.handle(stmt, ctx)
            finally:
                ctx.statement_typechecker = previous_typechecker
