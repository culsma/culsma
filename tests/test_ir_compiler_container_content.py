from __future__ import annotations

from culsma.common.source import Span
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.parser.ast_nodes import Arg, Program, ProtocolDecl, StepCall, StringLiteral


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def test_container_content_sugar_lowers_to_canonical_ir():
    """CF-CNT-003: sugar forms lower to canonical constructors and IR remains sugar-free."""
    span = Span(line=1, col=1, start=0, end=1)
    ast = Program(
        protocols=[
            ProtocolDecl(
                name="T",
                statements=[
                    StepCall(name="tube", args=[Arg(name="label", value=StringLiteral("T1", span=span), span=span)], span=span),
                    StepCall(name="well", args=[Arg(name="label", value=StringLiteral("A1", span=span), span=span)], span=span),
                    StepCall(name="chamber", args=[Arg(name="label", value=StringLiteral("C1", span=span), span=span)], span=span),
                    StepCall(name="surface", args=[Arg(name="label", value=StringLiteral("S1", span=span), span=span)], span=span),
                    StepCall(name="blood", args=[Arg(name="name", value=StringLiteral("S1", span=span), span=span)], span=span),
                    StepCall(name="reagent", args=[Arg(name="name", value=StringLiteral("R1", span=span), span=span)], span=span),
                    StepCall(name="buffer", args=[Arg(name="name", value=StringLiteral("B1", span=span), span=span)], span=span),
                ],
                span=span,
            )
        ],
        span=span,
    )
    ir = compile_to_ir(ast)
    steps = [s for s in ir.protocols[0].statements if s.__class__.__name__ == "IRStep"]
    assert [s.name for s in steps] == [
        "AllocContainer",
        "AllocContainer",
        "AllocContainer",
        "AllocContainer",
        "DefineContent",
        "DefineContent",
        "DefineContent",
    ]
    lowered_kinds = []
    for step in steps:
        arg_by_name = {a.name: a.value for a in step.args}
        if "kind" in arg_by_name and arg_by_name["kind"].__class__.__name__ == "IRString":
            lowered_kinds.append(arg_by_name["kind"].value)
    assert "tube" in lowered_kinds
    assert "well" in lowered_kinds
    assert "chamber" in lowered_kinds
    assert "surface" in lowered_kinds
    assert "blood" in lowered_kinds
    assert "reagent" in lowered_kinds
    assert "buffer" in lowered_kinds
