from __future__ import annotations

from culsma.common.source import Span
from culsma.parser.ast_nodes import (
    Arg,
    BinaryOp,
    CallExpr,
    Identifier,
    ListLiteral,
    Program,
    ProtocolDecl,
    Quantity,
    RepeatStatement,
    StepCall,
    StringLiteral,
    WithEnvStmt,
)
from culsma.pipeline.compile.callable import CallableLowering
from culsma.pipeline.compile.context import BlockContext, CompileSession
from culsma.pipeline.compile.expressions import ExprCompiler
from culsma.pipeline.compile.repeat_control import RepeatControlLowerer
from culsma.pipeline.compile.schedule import ScheduleEvaluator
from culsma.pipeline.compile.static_control import StaticControlClassifier
from culsma.pipeline.compile.statements import StatementCompiler, StatementLoweringContext
from culsma.pipeline.compile.targets import TargetResolver
from culsma.pipeline.ir_nodes import IRRepeat, IRStep


SPAN = Span(line=1, col=1, start=0, end=1)


def q(value: float, unit: str | None = None) -> Quantity:
    return Quantity(value=value, unit=unit)


def arg(name: str, value):
    return Arg(name=name, value=value)


def schedule(*args: Arg) -> CallExpr:
    return CallExpr(name="schedule", args=list(args))


def _statement_compiler() -> StatementCompiler:
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
        static_control_classifier=StaticControlClassifier(),
        repeat_control_lowerer=RepeatControlLowerer(),
    )


def _lowering_ctx(
    compiler: StatementCompiler,
    *,
    block_context: BlockContext | None = None,
) -> StatementLoweringContext:
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
        static_control_classifier=compiler.static_control_classifier,
        repeat_control_lowerer=compiler.repeat_control_lowerer,
    )


def _step() -> StepCall:
    return StepCall(
        name="observe",
        args=[Arg(name="sample", value=Identifier("sample", span=SPAN), span=SPAN)],
        span=SPAN,
    )


def test_static_control_classifier_public_schedule_methods():
    classifier = StaticControlClassifier()
    ctx = BlockContext(
        scope_id="p0",
        let_bindings={"sched": schedule(arg("start", q(1)), arg("end", Identifier("cycles")), arg("step", q(1)))},
        param_names={"cycles"},
    )

    args = classifier.schedule_args(Identifier("sched"), ctx=ctx)
    assert args is not None
    assert isinstance(args["end"], Identifier)
    assert classifier.schedule_mode(args) == "discrete"
    assert classifier.resolve_bound_expr(Identifier("sched"), ctx=ctx) is ctx.let_bindings["sched"]


def test_static_control_classifier_finds_unresolved_params_inside_nested_expressions():
    classifier = StaticControlClassifier()
    ctx = BlockContext(scope_id="p0", param_names={"cycles"})
    expr = ListLiteral(elements=[BinaryOp(op="+", left=Identifier("cycles"), right=q(1))])

    assert classifier.contains_unresolved_param_reference(expr, ctx=ctx)
    assert classifier.can_defer_repeat_count(BinaryOp(op="+", left=Identifier("cycles"), right=q(1)), ctx=ctx)
    assert not classifier.contains_unresolved_param_reference(Identifier("local"), ctx=ctx)


def test_static_control_classifier_defer_decisions_for_schedule_and_env_boundary():
    classifier = StaticControlClassifier()
    ctx = BlockContext(scope_id="p0", param_names={"duration", "cycles"})

    discrete = schedule(arg("start", q(1)), arg("end", Identifier("cycles")), arg("step", q(1)))
    continuous = schedule(
        arg("start", q(0, "min")),
        arg("duration", Identifier("duration")),
        arg("mode", StringLiteral("continuous")),
    )
    env = WithEnvStmt(env_args=[arg("duration", Identifier("duration"))])
    thermal_env = WithEnvStmt(
        env_args=[
            arg(
                "thermal",
                CallExpr(name="thermal_program", args=[arg("duration", Identifier("duration"))]),
            )
        ]
    )

    assert classifier.can_defer_discrete_schedule(discrete, ctx=ctx)
    assert classifier.can_defer_continuous_schedule(continuous, ctx=ctx)
    assert classifier.can_defer_env_time_boundary(env, ctx=ctx)
    assert classifier.can_defer_env_time_boundary(thermal_env, ctx=ctx)


def test_static_control_classifier_defers_open_time_schedule_when_env_boundary_is_deferred():
    classifier = StaticControlClassifier()
    ctx = BlockContext(scope_id="p0", env_time_boundary_deferred=True)
    open_time_schedule = schedule(arg("start", q(0, "min")), arg("step", q(10, "min")))

    assert classifier.can_defer_discrete_schedule(open_time_schedule, ctx=ctx)


def test_schedule_evaluator_public_boundary_methods_replace_cross_module_private_calls():
    evaluator = ScheduleEvaluator()
    ctx = BlockContext(scope_id="p0", let_bindings={"duration": q(3, "min")})
    env = WithEnvStmt(env_args=[arg("duration", Identifier("duration"))])

    assert evaluator.resolve_bound_expr(Identifier("duration"), ctx=ctx) == q(3, "min")
    assert evaluator.extract_env_time_boundary(env, ctx=ctx) == q(3, "min")
    assert evaluator.supports_runtime_boolean_surface(BinaryOp("==", Identifier("x"), q(1)))
    assert evaluator.is_time_point(q(3, "min"))


def test_repeat_control_lowerer_public_count_repeat_schedule_expr_marks_plan_static_repeat_count():
    repeat = RepeatStatement(times=Identifier("cycles"))
    lowered = RepeatControlLowerer().count_repeat_schedule_expr(repeat)

    assert lowered.name == "schedule"
    args = {item.name: item.value for item in lowered.args}
    assert args["start"] == q(1)
    assert args["end"] == Identifier("cycles")
    assert args["step"] == q(1)
    assert args["__repeat_count"].value is True


def test_repeat_control_lowerer_public_methods_cover_repeat_lowering_shapes():
    compiler = _statement_compiler()
    ctx = _lowering_ctx(compiler)
    lowerer = RepeatControlLowerer()

    list_repeat = RepeatStatement(
        binding="i",
        iterable=ListLiteral(elements=[q(1), q(2)]),
        statements=[_step()],
        span=SPAN,
    )
    list_output = lowerer.lower_binding_repeat(list_repeat, ctx)
    assert [type(stmt) for stmt in list_output] == [IRStep, IRStep]

    direct_iterable_output = lowerer.lower_iterable_values(list_repeat, ctx, [q(1)])
    assert [type(stmt) for stmt in direct_iterable_output] == [IRStep]

    count_repeat = RepeatStatement(times=q(2), statements=[_step()], span=SPAN)
    count_output = lowerer.lower_count_repeat(count_repeat, ctx)
    assert [type(stmt) for stmt in count_output] == [IRStep, IRStep]

    continuous_repeat = RepeatStatement(
        binding="t",
        iterable=schedule(
            arg("start", q(0, "min")),
            arg("duration", q(30, "min")),
            arg("mode", StringLiteral("continuous")),
        ),
        statements=[_step()],
        span=SPAN,
    )
    continuous_output = lowerer.lower_continuous_schedule(continuous_repeat, ctx)
    assert [type(stmt) for stmt in continuous_output] == [IRStep]

    deferred_ctx = _lowering_ctx(compiler, block_context=BlockContext(scope_id="p0", param_names={"cycles"}))
    formal_count = RepeatStatement(times=Identifier("cycles", span=SPAN), statements=[_step()], span=SPAN)
    deferred_output = lowerer.lower_deferred_static_repeat(
        formal_count,
        deferred_ctx,
        lowerer.count_repeat_schedule_expr(formal_count),
        binding="__repeat_index_p0_s0",
    )
    assert len(deferred_output) == 1
    assert isinstance(deferred_output[0], IRRepeat)

    lower_repeat_output = lowerer.lower_repeat(formal_count, deferred_ctx)
    assert len(lower_repeat_output) == 1
    assert isinstance(lower_repeat_output[0], IRRepeat)
