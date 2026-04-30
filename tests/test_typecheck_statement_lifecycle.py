from __future__ import annotations

from culsma.common.source import Span
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRArg,
    IRIdentifier,
    IRLet,
    IRQuantity,
    IRStatement,
    IRStep,
    IRString,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS
from culsma.pipeline.typecheck.context import TypecheckContext
from culsma.pipeline.typecheck.statements import (
    BaseTypecheckStatementHandler,
    ChildStatementBlock,
    StatementTypechecker,
    TypecheckStatementState,
)


SPAN = Span(line=1, col=1, start=0, end=1)


def _ctx() -> TypecheckContext:
    return TypecheckContext(
        operation_specs=BUILTIN_OPERATION_SPECS,
        diagnostics=[],
        expr_bindings={},
    )


def _codes(ctx: TypecheckContext) -> list[str]:
    return [diagnostic.code for diagnostic in ctx.diagnostics]


class RecordingTypecheckHandler(BaseTypecheckStatementHandler):
    def __init__(self, *, stop_at: str | None = None) -> None:
        self.events: list[str] = []
        self.stop_at = stop_at

    def _record(self, name: str, state: TypecheckStatementState) -> None:
        self.events.append(name)
        if self.stop_at == name:
            state.stop = True

    def prepare(self, stmt: IRStatement, ctx: TypecheckContext) -> TypecheckStatementState:
        del stmt, ctx
        state = TypecheckStatementState()
        self._record("prepare", state)
        return state

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        del stmt, ctx
        self._record("validate_pre_binding_contracts", state)

    def update_or_derive_bindings(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        del stmt, ctx
        self._record("update_or_derive_bindings", state)

    def check_child_expressions(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        del stmt, ctx
        self._record("check_child_expressions", state)

    def check_statement_specific_rules(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        del stmt, ctx
        self._record("check_statement_specific_rules", state)

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ):
        del stmt, ctx
        self._record("iter_child_blocks", state)
        return (ChildStatementBlock([], {}),)

    def apply_post_child_effects(
        self,
        stmt: IRStatement,
        ctx: TypecheckContext,
        state: TypecheckStatementState,
    ) -> None:
        del stmt, ctx
        self._record("apply_post_child_effects", state)

    def recurse(self, child: ChildStatementBlock, ctx: TypecheckContext) -> None:
        del child, ctx
        self.events.append("recurse_child_block")


def test_base_typecheck_handler_runs_lifecycle_in_documented_order():
    handler = RecordingTypecheckHandler()

    handler.handle(IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN), _ctx())

    assert handler.events == [
        "prepare",
        "validate_pre_binding_contracts",
        "update_or_derive_bindings",
        "check_child_expressions",
        "check_statement_specific_rules",
        "iter_child_blocks",
        "recurse_child_block",
        "apply_post_child_effects",
    ]


def test_base_typecheck_handler_stop_skips_later_phases():
    handler = RecordingTypecheckHandler(stop_at="check_child_expressions")

    handler.handle(IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN), _ctx())

    assert handler.events == [
        "prepare",
        "validate_pre_binding_contracts",
        "update_or_derive_bindings",
        "check_child_expressions",
    ]


def test_statement_typechecker_dispatches_by_exact_ir_statement_type():
    handler = RecordingTypecheckHandler()
    typechecker = StatementTypechecker(handlers_by_type={IRLet: handler})

    typechecker.typecheck_list(
        [
            IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN),
            IRStep(id="s1", name="agit", args=[], span=SPAN),
        ],
        _ctx(),
    )

    assert handler.events.count("prepare") == 1


def test_let_handler_updates_local_name_table_for_later_assignment_checks():
    ctx = _ctx()
    typechecker = StatementTypechecker()

    typechecker.typecheck_list(
        [
            IRLet(id="s0", name="total", value=IRQuantity(1.0, "uL", SPAN), span=SPAN),
            IRAssign(id="s1", target=IRIdentifier("total", SPAN), value=IRString("bad", SPAN), span=SPAN),
        ],
        ctx,
    )

    assert ctx.expr_bindings["total"] == IRQuantity(1.0, "uL", SPAN)
    assert "TYPE_LOCAL_ASSIGN_MISMATCH" in _codes(ctx)


def test_child_block_local_name_table_does_not_leak_to_parent():
    ctx = _ctx()
    typechecker = StatementTypechecker()

    typechecker.typecheck_list(
        [
            IRWithConstraint(
                id="s0",
                statements=[
                    IRLet(id="s0.0", name="inner", value=IRQuantity(1.0, "uL", SPAN), span=SPAN),
                ],
                span=SPAN,
            ),
            IRAssign(id="s1", target=IRIdentifier("inner", SPAN), value=IRQuantity(2.0, "uL", SPAN), span=SPAN),
        ],
        ctx,
    )

    assert "inner" not in ctx.expr_bindings
    assert "TYPE_LOCAL_ASSIGN_TARGET_FORBIDDEN" in _codes(ctx)


def test_direct_statement_typecheck_recurses_into_child_blocks():
    ctx = _ctx()

    StatementTypechecker().typecheck_statement(
        IRWithConstraint(
            id="s0",
            statements=[
                IRStep(
                    id="s0.0",
                    name="agit",
                    args=[IRArg(name="duration", value=IRQuantity(5.0, "uL", SPAN), span=SPAN)],
                    span=SPAN,
                )
            ],
            span=SPAN,
        ),
        ctx,
    )

    assert "TYPE_DIMENSION_MISMATCH" in _codes(ctx)


def test_with_env_handler_checks_environment_argument_dimensions():
    ctx = _ctx()

    StatementTypechecker().typecheck_statement(
        IRWithEnv(
            id="s0",
            env_args=[IRArg(name="duration", value=IRQuantity(5.0, "uL", SPAN), span=SPAN)],
            statements=[],
            span=SPAN,
        ),
        ctx,
    )

    assert "TYPE_ENV_DURATION_DIMENSION_MISMATCH" in _codes(ctx)


def test_step_handler_checks_operation_argument_dimensions():
    ctx = _ctx()

    StatementTypechecker().typecheck_statement(
        IRStep(
            id="s0",
            name="agit",
            args=[IRArg(name="duration", value=IRQuantity(5.0, "uL", SPAN), span=SPAN)],
            span=SPAN,
        ),
        ctx,
    )

    assert "TYPE_DIMENSION_MISMATCH" in _codes(ctx)
