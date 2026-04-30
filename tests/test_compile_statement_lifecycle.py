from __future__ import annotations

import pytest

from culsma.common.source import Span
from culsma.parser.ast_nodes import (
    Arg,
    AssignStatement,
    Identifier,
    IncludeStatement,
    LetStatement,
    Program,
    ProtocolDecl,
    Quantity,
    RepeatStatement,
    Statement,
    StepCall,
)
from culsma.pipeline.compile.callable import CallableLowering
from culsma.pipeline.compile.context import BlockContext, CompileSession
from culsma.pipeline.compile.expressions import ExprCompiler
from culsma.pipeline.compile.schedule import ScheduleEvaluator
from culsma.pipeline.compile.statements import (
    BaseStatementCompileHandler,
    StatementCompiler,
    StatementLoweringContext,
    StatementLoweringState,
)
from culsma.pipeline.compile.targets import TargetResolver
from culsma.pipeline.ir_nodes import IRAssign, IRInclude, IRLet


SPAN = Span(line=1, col=1, start=0, end=1)


def _compiler(ast: Program | None = None) -> StatementCompiler:
    if ast is None:
        ast = Program(protocols=[ProtocolDecl(name="T", span=SPAN)], span=SPAN)
    session = CompileSession.from_program(ast)
    callable_lowering = CallableLowering(session=session)
    expr_compiler = ExprCompiler(callable_lowering=callable_lowering)
    return StatementCompiler(
        session=session,
        expr_compiler=expr_compiler,
        callable_lowering=callable_lowering,
        target_resolver=TargetResolver(session=session),
        schedule_evaluator=ScheduleEvaluator(),
    )


def _lowering_ctx(compiler: StatementCompiler, *, block_context: BlockContext | None = None) -> StatementLoweringContext:
    return StatementLoweringContext(
        stmt_id="p0.s0",
        stmt_index=0,
        block_context=block_context if block_context is not None else BlockContext(scope_id="p0"),
        statement_compiler=compiler,
        session=compiler.session,
        expr_compiler=compiler.expr_compiler,
        callable_lowering=compiler.callable_lowering,
        target_resolver=compiler.target_resolver,
        schedule_evaluator=compiler.schedule_evaluator,
    )


class RecordingCompileHandler(BaseStatementCompileHandler):
    def __init__(self, *, finish_at: str | None = None) -> None:
        self.events: list[str] = []
        self.finish_at = finish_at

    def _record(self, name: str, state: StatementLoweringState) -> None:
        self.events.append(name)
        if self.finish_at == name:
            state.output = []

    def prepare(self, stmt: Statement, lowering_ctx: StatementLoweringContext) -> StatementLoweringState:
        state = super().prepare(stmt, lowering_ctx)
        self._record("prepare", state)
        return state

    def resolve_source_form(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx
        self._record("resolve_source_form", state)

    def validate_source_shape(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx
        self._record("validate_source_shape", state)

    def apply_state_before_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ) -> None:
        del stmt, lowering_ctx
        self._record("apply_state_before_lowering", state)

    def lower_prefix_ir(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ):
        del stmt, lowering_ctx
        self._record("lower_prefix_ir", state)
        return []

    def lower_current_or_children(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
    ):
        del stmt, lowering_ctx
        self._record("lower_current_or_children", state)
        return []

    def apply_state_after_lowering(
        self,
        stmt: Statement,
        lowering_ctx: StatementLoweringContext,
        state: StatementLoweringState,
        output,
    ) -> None:
        del stmt, lowering_ctx, output
        self._record("apply_state_after_lowering", state)


def test_base_statement_compile_handler_runs_lifecycle_in_documented_order():
    compiler = _compiler()
    handler = RecordingCompileHandler()

    handler.handle(LetStatement(name="x", value=Quantity(1.0, None, span=SPAN), span=SPAN), _lowering_ctx(compiler))

    assert handler.events == [
        "prepare",
        "resolve_source_form",
        "validate_source_shape",
        "apply_state_before_lowering",
        "lower_prefix_ir",
        "lower_current_or_children",
        "apply_state_after_lowering",
    ]


def test_base_statement_compile_handler_final_output_skips_later_phases():
    compiler = _compiler()
    handler = RecordingCompileHandler(finish_at="validate_source_shape")

    output = handler.handle(
        LetStatement(name="x", value=Quantity(1.0, None, span=SPAN), span=SPAN),
        _lowering_ctx(compiler),
    )

    assert output == []
    assert handler.events == ["prepare", "resolve_source_form", "validate_source_shape"]


def test_statement_compiler_dispatch_records_compile_analysis_from_ir_output():
    ast = Program(
        protocols=[
            ProtocolDecl(name="Main", span=SPAN),
            ProtocolDecl(name="Shared", span=SPAN),
        ],
        span=SPAN,
    )
    compiler = _compiler(ast)
    ctx = BlockContext(scope_id="p0")

    output = compiler.compile_list([IncludeStatement(name="Shared", span=SPAN)], ctx=ctx)
    analysis = compiler.session.analysis_builder.build(protocol_ids=["p0", "p1"])

    assert output == [IRInclude(id="p0.s0", name="Shared", args=[], span=SPAN)]
    assert analysis.protocols["p0"].include_targets == {"p0.s0": "p1"}


def test_let_handler_updates_compile_time_state_before_lowering():
    compiler = _compiler()
    ctx = BlockContext(scope_id="p0")

    output = compiler.compile(
        LetStatement(name="x", value=Quantity(3.0, None, span=SPAN), span=SPAN),
        ctx=ctx,
        stmt_index=0,
    )

    assert isinstance(output[0], IRLet)
    assert ctx.local_names == {"x"}
    assert ctx.const_env["x"] == 3.0
    assert ctx.let_bindings["x"] == Quantity(3.0, None, span=SPAN)


def test_assign_handler_validates_local_target_before_lowering():
    compiler = _compiler()
    ctx = BlockContext(scope_id="p0")

    with pytest.raises(ValueError, match="previously declared"):
        compiler.compile(
            AssignStatement(
                target=Identifier("x", span=SPAN),
                value=Quantity(2.0, None, span=SPAN),
                span=SPAN,
            ),
            ctx=ctx,
            stmt_index=0,
        )

    ctx.local_names.add("x")
    output = compiler.compile(
        AssignStatement(
            target=Identifier("x", span=SPAN),
            value=Quantity(2.0, None, span=SPAN),
            span=SPAN,
        ),
        ctx=ctx,
        stmt_index=0,
    )

    assert isinstance(output[0], IRAssign)
    assert ctx.const_env["x"] == 2.0


def test_step_call_handler_rejects_hold_before_lowering_ir():
    compiler = _compiler()

    with pytest.raises(ValueError, match="only valid as the sole statement inside with env"):
        compiler.compile(
            StepCall(
                name="hold",
                args=[Arg(name="sample", value=Identifier("tube", span=SPAN), span=SPAN)],
                span=SPAN,
            ),
            ctx=BlockContext(scope_id="p0"),
            stmt_index=0,
        )


def test_repeat_handler_applies_post_lowering_runtime_mutation_invalidation():
    compiler = _compiler()
    ctx = BlockContext(
        scope_id="p0",
        const_env={"x": 1.0},
        let_bindings={"x": Quantity(1.0, None, span=SPAN)},
        local_names={"x"},
    )
    repeat = RepeatStatement(
        times=Quantity(1.0, None, span=SPAN),
        statements=[
            AssignStatement(
                target=Identifier("x", span=SPAN),
                value=Quantity(2.0, None, span=SPAN),
                span=SPAN,
            )
        ],
        span=SPAN,
    )

    compiler.compile(repeat, ctx=ctx, stmt_index=0)

    assert "x" not in ctx.const_env
    assert "x" not in ctx.let_bindings
