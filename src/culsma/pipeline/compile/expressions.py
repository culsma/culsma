"""Expression lowering for AST -> IR compile."""

from __future__ import annotations

from culsma.parser.ast_nodes import (
    Arg,
    BinaryOp,
    BooleanLiteral,
    CallExpr,
    Expression,
    GroupExpr,
    Identifier,
    IndexExpr,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    PairExpr,
    ParamDecl,
    PlateSelectorExpr,
    Quantity,
    RecordLiteral,
    SourcePartitionExpr,
    StringLiteral,
    UnaryOp,
)
from culsma.pipeline.ir_nodes import (
    IRArg,
    IRBinary,
    IRBoolean,
    IRCall,
    IRExpr,
    IRGroup,
    IRIdentifier,
    IRIndex,
    IRMember,
    IRList,
    IRPlateSelector,
    IRParam,
    IRPair,
    IRQuantity,
    IRRecord,
    IRSelectorRegion,
    IRSourcePartitionRef,
    IRString,
    IRUnary,
)

from .callable import CallableLowering
from .context import _require_span


class ExprCompiler:
    def __init__(self, *, callable_lowering: CallableLowering) -> None:
        self.callable_lowering = callable_lowering

    def compile(self, expr: Expression) -> IRExpr:
        _require_span(expr, f"expr[{type(expr).__name__}]")
        if isinstance(expr, Quantity):
            return IRQuantity(value=expr.value, unit=expr.unit, span=expr.span)
        if isinstance(expr, StringLiteral):
            return IRString(value=expr.value, span=expr.span)
        if isinstance(expr, BooleanLiteral):
            return IRBoolean(value=expr.value, span=expr.span)
        if isinstance(expr, Identifier):
            return IRIdentifier(name=expr.name, span=expr.span)
        if isinstance(expr, ListLiteral):
            return IRList(elements=[self.compile(e) for e in expr.elements], span=expr.span)
        if isinstance(expr, RecordLiteral):
            return IRRecord(entries={key: self.compile(value) for key, value in expr.entries.items()}, span=expr.span)
        if isinstance(expr, GroupExpr):
            return IRGroup(elements=[self.compile(e) for e in expr.elements], span=expr.span)
        if isinstance(expr, CallExpr):
            if expr.name == "series":
                raise ValueError("series(...) is only valid inside a mutation source list")
            if expr.name == "thermal_program":
                _validate_thermal_program_call(expr)
            lowered_name, lowered_args = self.callable_lowering.lower_callable(
                expr.name,
                expr.args,
                expr.span,
            )
            return IRCall(
                name=lowered_name,
                args=[self.compile_arg(arg) for arg in lowered_args],
                span=expr.span,
            )
        if isinstance(expr, PlateSelectorExpr):
            return IRPlateSelector(
                base=IRIdentifier(name=expr.base.name, span=expr.base.span),
                regions=[
                    IRSelectorRegion(start=region.start, end=region.end, span=region.span)
                    for region in expr.regions
                ],
                span=expr.span,
            )
        if isinstance(expr, IndexExpr):
            return IRIndex(
                base=self.compile(expr.base),
                index=self.compile(expr.index),
                span=expr.span,
            )
        if isinstance(expr, MemberExpr):
            return IRMember(
                base=self.compile(expr.base),
                member=expr.member,
                span=expr.span,
            )
        if isinstance(expr, MethodCallExpr):
            return IRCall(
                name=expr.method,
                args=self.compile_method_call_expr_args(expr),
                span=expr.span,
            )
        if isinstance(expr, SourcePartitionExpr):
            return IRSourcePartitionRef(
                source=self.compile(expr.source),
                program=self.compile(expr.program),
                index=self.compile(expr.index),
                span=expr.span,
            )
        if isinstance(expr, PairExpr):
            return IRPair(
                left=self.compile(expr.left),
                right=self.compile(expr.right),
                span=expr.span,
            )
        if isinstance(expr, UnaryOp):
            return IRUnary(op=expr.op, operand=self.compile(expr.operand), span=expr.span)
        if isinstance(expr, BinaryOp):
            return IRBinary(
                op=expr.op,
                left=self.compile(expr.left),
                right=self.compile(expr.right),
                span=expr.span,
            )
        raise TypeError(f"Unsupported expression type: {type(expr).__name__}")

    def compile_arg(self, arg: Arg) -> IRArg:
        _require_span(arg, f"arg[{arg.name}]")
        return IRArg(
            name=arg.name,
            value=self.compile(arg.value),
            span=arg.span,
        )

    def compile_param(self, param: ParamDecl) -> IRParam:
        _require_span(param, f"param[{param.name}]")
        return IRParam(
            name=param.name,
            default=self.compile(param.default) if param.default is not None else None,
            span=param.span,
        )

    def compile_method_call_expr_args(self, expr: MethodCallExpr) -> list[IRArg]:
        return [
            IRArg(name="self", value=self.compile(expr.base), span=expr.base.span),
            *[
                IRArg(name=f"arg{idx}", value=self.compile(arg), span=arg.span)
                for idx, arg in enumerate(expr.args)
            ],
        ]

    def compile_method_call_step_args(self, expr: MethodCallExpr) -> list[IRArg]:
        return self.compile_method_call_expr_args(expr)


def _validate_thermal_program_call(expr: CallExpr) -> None:
    arg_names = {arg.name for arg in expr.args}
    allowed = {"from", "to", "duration"}
    forbidden = {
        "cycles",
        "cycle",
        "stage",
        "stages",
        "denature",
        "anneal",
        "extend",
        "emit",
        "cadence",
        "every",
        "total",
    }
    forbidden_hit = sorted(arg_names & forbidden)
    if forbidden_hit:
        raise ValueError(f"thermal_program no longer accepts legacy args: {', '.join(forbidden_hit)}")
    unknown = sorted(arg_names - allowed)
    if unknown:
        raise ValueError(f"thermal_program accepts only from/to/duration, got: {', '.join(unknown)}")
    if "from" not in arg_names:
        raise ValueError("thermal_program requires 'from'")
    if "duration" not in arg_names:
        raise ValueError("thermal_program requires 'duration'")
