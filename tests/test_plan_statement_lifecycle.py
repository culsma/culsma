from __future__ import annotations

from culsma.common.source import Span
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRArg,
    IRCall,
    IRIdentifier,
    IRInclude,
    IRLet,
    IRProtocol,
    IRQuantity,
    IRRepeat,
    IRStatement,
    IRStep,
)
from culsma.pipeline.plan.context import PlanLoweringContext
from culsma.pipeline.plan.references import DEFAULT_PLAN_REFERENCE_RESOLVER
from culsma.pipeline.plan.serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER
from culsma.pipeline.plan.statements import (
    BasePlanStatementHandler,
    PlanStatementLowerer,
    PlanStatementLoweringState,
)


SPAN = Span(line=1, col=1, start=0, end=1)


def _ctx(
    *,
    protocols_by_name: dict[str, IRProtocol] | None = None,
    local_env: dict | None = None,
    protected_names: set[str] | None = None,
) -> PlanLoweringContext:
    serializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER
    reference_resolver = DEFAULT_PLAN_REFERENCE_RESOLVER
    lowerer = PlanStatementLowerer(
        serializer=serializer,
        reference_resolver=reference_resolver,
    )
    return PlanLoweringContext(
        protocols_by_name={} if protocols_by_name is None else protocols_by_name,
        diagnostics=[],
        local_env={} if local_env is None else dict(local_env),
        protected_names=set() if protected_names is None else set(protected_names),
        protocol_name="Root",
        caller_stack=["Root"],
        gate_base={"protocol_name": "Root"},
        statement_lowerer=lowerer,
        serializer=serializer,
        reference_resolver=reference_resolver,
        step_id_prefix="",
        call_path=[],
    )


class RecordingPlanHandler(BasePlanStatementHandler):
    def __init__(self, *, finish_at: str | None = None) -> None:
        self.events: list[str] = []
        self.finish_at = finish_at

    def _record(self, name: str, state: PlanStatementLoweringState) -> None:
        self.events.append(name)
        if self.finish_at == name:
            state.output = []

    def prepare(self, _stmt: IRStatement, _ctx: PlanLoweringContext) -> PlanStatementLoweringState:
        state = PlanStatementLoweringState()
        self._record("prepare", state)
        return state

    def validate_pre_lowering_rules(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> None:
        self._record("validate_pre_lowering_rules", state)

    def update_or_derive_local_env(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> None:
        self._record("update_or_derive_local_env", state)

    def serialize_child_expressions(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> None:
        self._record("serialize_child_expressions", state)

    def lower_current_or_children(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ):
        self._record("lower_current_or_children", state)
        return []

    def apply_post_lowering_effects(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
        _output,
    ) -> None:
        self._record("apply_post_lowering_effects", state)


def test_base_plan_handler_runs_lifecycle_in_documented_order():
    handler = RecordingPlanHandler()

    handler.handle(IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN), _ctx())

    assert handler.events == [
        "prepare",
        "validate_pre_lowering_rules",
        "update_or_derive_local_env",
        "serialize_child_expressions",
        "lower_current_or_children",
        "apply_post_lowering_effects",
    ]


def test_base_plan_handler_final_output_skips_later_phases():
    handler = RecordingPlanHandler(finish_at="serialize_child_expressions")

    output = handler.handle(IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN), _ctx())

    assert output == []
    assert handler.events == [
        "prepare",
        "validate_pre_lowering_rules",
        "update_or_derive_local_env",
        "serialize_child_expressions",
    ]


def test_plan_statement_lowerer_dispatches_by_exact_ir_statement_type():
    handler = RecordingPlanHandler()
    lowerer = PlanStatementLowerer(handlers_by_type={IRLet: handler})

    output = lowerer.lower_list(
        [
            IRLet(id="s0", name="x", value=IRQuantity(1.0, None, SPAN), span=SPAN),
            IRStep(id="s1", name="Step", args=[], span=SPAN),
        ],
        _ctx(),
    )

    assert output == []
    assert handler.events.count("prepare") == 1


def test_let_handler_serializes_plain_let_binding_for_later_step_payloads():
    ctx = _ctx()

    steps = ctx.statement_lowerer.lower_list(
        [
            IRLet(id="s0", name="amount", value=IRQuantity(5.0, "uL", SPAN), span=SPAN),
            IRStep(
                id="s1",
                name="Step",
                args=[IRArg(name="v", value=IRIdentifier("amount", SPAN), span=SPAN)],
                span=SPAN,
            ),
        ],
        ctx,
    )

    assert steps[0].op == "Step"
    assert steps[0].args["v"]["kind"] == "IRQuantity"
    assert steps[0].args["v"]["value"] == 5.0
    assert steps[0].args["v"]["unit"] == "uL"


def test_let_handler_lowers_let_bound_sep_call_to_runtime_step():
    ctx = _ctx()

    steps = ctx.statement_lowerer.lower_list(
        [
            IRLet(
                id="s0",
                name="sep_group",
                value=IRCall(
                    name="sep",
                    args=[
                        IRArg(name="sample", value=IRIdentifier("tube", SPAN), span=SPAN),
                        IRArg(name="program", value=IRIdentifier("prog", SPAN), span=SPAN),
                    ],
                    span=SPAN,
                ),
                span=SPAN,
            )
        ],
        ctx,
    )

    assert [step.op for step in steps] == ["sep"]
    assert steps[0].args["bind"] == "sep_group"


def test_include_handler_expands_referenced_protocol_steps():
    child = IRProtocol(
        id="p1",
        name="Child",
        statements=[IRStep(id="p1.s0", name="StepChild", args=[], span=SPAN)],
        span=SPAN,
    )
    ctx = _ctx(protocols_by_name={"Root": IRProtocol(id="p0", name="Root", span=SPAN), "Child": child})

    steps = ctx.statement_lowerer.lower_list(
        [IRInclude(id="s0", name="Child", args=[], span=SPAN)],
        ctx,
    )

    assert [step.op for step in steps] == ["StepChild"]


def test_repeat_handler_embeds_linearized_body_steps_and_invalidates_runtime_mutations():
    ctx = _ctx(local_env={"x": {"kind": "IRIdentifier", "name": "x"}})

    steps = ctx.statement_lowerer.lower_list(
        [
            IRRepeat(
                id="s0",
                binding="item",
                iterable=IRIdentifier("items", SPAN),
                statements=[
                    IRAssign(
                        id="s0.0",
                        target=IRIdentifier("x", SPAN),
                        value=IRQuantity(2.0, None, SPAN),
                        span=SPAN,
                    ),
                    IRStep(id="s0.1", name="Step2", args=[], span=SPAN),
                ],
                span=SPAN,
            )
        ],
        ctx,
    )

    assert steps[0].op == "repeat_bind"
    assert [body.op for body in steps[0].args["body_steps"]] == ["assign_local", "Step2"]
    assert steps[0].args["body_steps"][1].deps == [steps[0].args["body_steps"][0].step_id]
    assert ctx.local_env["x"] == {"kind": "IRIdentifier", "name": "x"}
