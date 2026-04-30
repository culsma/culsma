from __future__ import annotations

from typing import Iterable

from culsma.pipeline.analysis import CompileAnalysis, ProtocolAnalysis
from culsma.pipeline.ir_nodes import (
    IRArg,
    IRIdentifier,
    IRInclude,
    IRLet,
    IRList,
    IRQuantity,
    IRRepeat,
    IRStatement,
    IRStep,
    IRWithConstraint,
)
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS
from culsma.pipeline.validate.statements import (
    BaseStatementHandler,
    ChildBlock,
    ChildExpression,
    HandlerState,
    IncludeHandler,
    LetHandler,
    RepeatHandler,
    StatementValidationContext,
    StepHandler,
    WithConstraintHandler,
)


def _codes(ctx: StatementValidationContext) -> list[str]:
    return [diagnostic.code for diagnostic in ctx.diagnostics]


def _ctx(
    *,
    defined_names: set[str] | None = None,
    enforce_binding: bool = False,
    active_requirements: tuple[str, ...] = (),
    analysis: CompileAnalysis | None = None,
    protocol_analysis: ProtocolAnalysis | None = None,
) -> StatementValidationContext:
    if protocol_analysis is None:
        protocol_analysis = ProtocolAnalysis()
    if analysis is None:
        analysis = CompileAnalysis(protocols={"p0": protocol_analysis})
    return StatementValidationContext(
        literal_bindings={},
        expr_bindings={},
        group_bindings={},
        defined_names=set() if defined_names is None else set(defined_names),
        active_requirements=active_requirements,
        diagnostics=[],
        operations=BUILTIN_OPERATION_SPECS,
        analysis=analysis,
        protocol_analysis=protocol_analysis,
        enforce_binding=enforce_binding,
        content_whitelist_mode="strict",
        content_type_policy="required",
    )


class RecordingHandler(BaseStatementHandler):
    def __init__(self, *, stop_at: str | None = None) -> None:
        self.events: list[str] = []
        self.stop_at = stop_at

    def _record(self, name: str, state: HandlerState) -> None:
        self.events.append(name)
        if self.stop_at == name:
            state.stop = True

    def prepare(self, stmt: IRStatement, ctx: StatementValidationContext) -> HandlerState:
        del stmt, ctx
        state = HandlerState()
        self._record("prepare", state)
        return state

    def validate_pre_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("pre_binding_contracts", state)

    def validate_bindings(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("bindings", state)

    def validate_post_binding_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("post_binding_contracts", state)

    def apply_state_before_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("state_before_children", state)

    def iter_child_expressions(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildExpression]:
        del stmt, ctx
        self._record("child_expressions", state)
        yield ChildExpression(IRIdentifier("sample"), "expr-node")

    def iter_child_blocks(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> Iterable[ChildBlock]:
        del stmt, ctx
        self._record("child_blocks", state)
        yield ChildBlock([])

    def validate_post_child_contracts(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("post_child_contracts", state)

    def apply_state_after_children(
        self,
        stmt: IRStatement,
        ctx: StatementValidationContext,
        state: HandlerState,
    ) -> None:
        del stmt, ctx
        self._record("state_after_children", state)

    def validate_expr(
        self,
        expr,
        ctx: StatementValidationContext,
        *,
        node_id: str | None,
    ) -> None:
        del expr, ctx
        self.events.append(f"validate_expr:{node_id}")

    def recurse(
        self,
        statements: list[IRStatement],
        ctx: StatementValidationContext,
        *,
        defined_names: set[str] | None = None,
        active_requirements: tuple[str, ...] | None = None,
    ) -> None:
        del statements, ctx, defined_names, active_requirements
        self.events.append("recurse")


def test_base_statement_handler_runs_the_lifecycle_in_documented_order():
    handler = RecordingHandler()
    handler.handle(IRStep(id="s0", name="append"), _ctx())

    assert handler.events == [
        "prepare",
        "pre_binding_contracts",
        "bindings",
        "post_binding_contracts",
        "state_before_children",
        "child_expressions",
        "validate_expr:expr-node",
        "child_blocks",
        "recurse",
        "post_child_contracts",
        "state_after_children",
    ]


def test_base_statement_handler_stop_state_skips_later_phases():
    handler = RecordingHandler(stop_at="pre_binding_contracts")
    handler.handle(IRStep(id="s0", name="append"), _ctx())

    assert handler.events == ["prepare", "pre_binding_contracts"]


def test_include_handler_publishes_compile_analysis_exports_as_state_effect():
    protocol_analysis = ProtocolAnalysis(include_targets={"inc0": "p1"})
    analysis = CompileAnalysis(
        protocols={
            "p0": protocol_analysis,
            "p1": ProtocolAnalysis(runtime_exports=frozenset({"shared_tube"})),
        }
    )
    ctx = _ctx(analysis=analysis, protocol_analysis=protocol_analysis)

    IncludeHandler().handle(IRInclude(id="inc0", name="Shared"), ctx)

    assert ctx.defined_names == {"shared_tube"}


def test_let_handler_checks_binding_before_publishing_runtime_name():
    ctx = _ctx(enforce_binding=True)

    LetHandler().handle(IRLet(id="let0", name="alias", value=IRIdentifier("unbound_tube")), ctx)

    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(ctx)
    assert ctx.expr_bindings["alias"] == IRIdentifier("unbound_tube")
    assert "alias" not in ctx.defined_names


def test_step_handler_unknown_step_stops_before_binding_and_expression_validation():
    ctx = _ctx(enforce_binding=True)
    stmt = IRStep(
        id="step0",
        name="UnknownOp",
        args=[IRArg(name="sample", value=IRIdentifier("unbound_tube"))],
    )

    StepHandler().handle(stmt, ctx)

    assert _codes(ctx) == ["SEM_UNKNOWN_STEP"]


def test_repeat_handler_recurses_with_loop_binding_in_child_scope():
    ctx = _ctx(enforce_binding=True)
    stmt = IRRepeat(
        id="repeat0",
        binding="item",
        iterable=IRList([]),
        statements=[
            IRStep(
                id="img0",
                name="img",
                args=[
                    IRArg(name="sample", value=IRIdentifier("item")),
                    IRArg(name="quantity", value=IRIdentifier("fluorescence")),
                ],
            )
        ],
    )

    RepeatHandler().handle(stmt, ctx)

    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(ctx)
    assert "item" not in ctx.defined_names


def test_with_constraint_handler_passes_active_requirements_to_child_block():
    ctx = _ctx(defined_names={"tube"})
    stmt = IRWithConstraint(
        id="constraint0",
        requirements=["preserve_boundary"],
        statements=[
            IRStep(
                id="img0",
                name="img",
                args=[
                    IRArg(name="sample", value=IRIdentifier("tube")),
                    IRArg(name="quantity", value=IRIdentifier("fluorescence")),
                ],
            )
        ],
    )

    WithConstraintHandler().handle(stmt, ctx)

    assert "SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH" in _codes(ctx)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(ctx)
