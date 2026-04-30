"""Callable lowering and readout normalization helpers."""

from __future__ import annotations

from culsma.parser.ast_nodes import Arg, CallExpr, Expression, GroupExpr, StepCall, StringLiteral
from culsma.pipeline.ir_nodes import IRLet

from .context import BlockContext, CompileSession
from .targets import _expand_group_like_target_expr, _is_group_like_ast

_SUGAR_TO_CANONICAL = {
    "container": "AllocContainer",
    "tube": "AllocContainer",
    "well": "AllocContainer",
    "chamber": "AllocContainer",
    "surface": "AllocContainer",
    "content": "DefineContent",
    "blood": "DefineContent",
    "reagent": "DefineContent",
    "buffer": "DefineContent",
}

_READOUT_FAMILY = {"img", "ecp", "phy"}


class CallableLowering:
    def __init__(self, *, session: CompileSession | None = None) -> None:
        self.session = session

    def lower_callable(self, name: str, args: list[Arg], span) -> tuple[str, list[Arg]]:
        return _lower_callable(name, args, span)

    def normalize_grouped_readout_call(
        self,
        call: CallExpr,
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], CallExpr]:
        if self.session is None:
            raise ValueError("CallableLowering.normalize_grouped_readout_call requires a compile session")
        return _normalize_grouped_readout_call(
            call,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            state=self.session.state,
        )

    def normalize_grouped_readout_stepcall(
        self,
        stmt: StepCall,
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], StepCall]:
        if self.session is None:
            raise ValueError("CallableLowering.normalize_grouped_readout_stepcall requires a compile session")
        return _normalize_grouped_readout_stepcall(
            stmt,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            state=self.session.state,
        )


def _find_named_arg(args: list[Arg], name: str) -> Arg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def _lower_callable(name: str, args: list[Arg], span) -> tuple[str, list[Arg]]:
    canonical_name = _SUGAR_TO_CANONICAL.get(name, name)
    args = list(args)
    existing = {arg.name for arg in args}

    def _inject(name: str, value: Expression) -> None:
        if name in existing:
            return
        args.insert(0, Arg(name=name, value=value, span=span))
        existing.add(name)

    if name == "tube":
        _inject("kind", StringLiteral(value="tube", span=span))
    elif name == "well":
        _inject("kind", StringLiteral(value="well", span=span))
        _inject("carrier_kind", StringLiteral(value="plate", span=span))
    elif name == "chamber":
        _inject("kind", StringLiteral(value="chamber", span=span))
    elif name == "surface":
        _inject("kind", StringLiteral(value="surface", span=span))
    elif name == "blood":
        _inject("kind", StringLiteral(value="biosample", span=span))
        _inject("type", StringLiteral(value="whole_blood", span=span))
    elif name == "reagent":
        _inject("kind", StringLiteral(value="reagent", span=span))
    elif name == "buffer":
        _inject("kind", StringLiteral(value="buffer", span=span))

    return canonical_name, args


def _normalize_grouped_readout_call(
    call: CallExpr,
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state,
) -> tuple[list[IRLet], CallExpr]:
    sample_arg = _find_named_arg(call.args, "sample")
    if sample_arg is None or not _is_group_like_ast(sample_arg.value, let_bindings):
        return [], call
    prefix, members = _expand_group_like_target_expr(
        sample_arg.value,
        stmt_id=stmt_id,
        let_bindings=let_bindings,
        state=state,
    )
    grouped_sample = GroupExpr(elements=members, span=sample_arg.value.span)
    rewritten_args = [
        Arg(name=arg.name, value=(grouped_sample if arg.name == "sample" else arg.value), span=arg.span)
        for arg in call.args
    ]
    return prefix, CallExpr(name=call.name, args=rewritten_args, span=call.span)


def _normalize_grouped_readout_stepcall(
    stmt: StepCall,
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state,
) -> tuple[list[IRLet], StepCall]:
    sample_arg = _find_named_arg(stmt.args, "sample")
    if sample_arg is None or not _is_group_like_ast(sample_arg.value, let_bindings):
        return [], stmt
    prefix, members = _expand_group_like_target_expr(
        sample_arg.value,
        stmt_id=stmt_id,
        let_bindings=let_bindings,
        state=state,
    )
    grouped_sample = GroupExpr(elements=members, span=sample_arg.value.span)
    rewritten_args = [
        Arg(name=arg.name, value=(grouped_sample if arg.name == "sample" else arg.value), span=arg.span)
        for arg in stmt.args
    ]
    return prefix, StepCall(name=stmt.name, args=rewritten_args, span=stmt.span)
