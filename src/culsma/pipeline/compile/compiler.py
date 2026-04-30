"""Program-level IR compiler orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from culsma.parser.ast_nodes import Program, ProtocolDecl
from culsma.pipeline.analysis import CompileAnalysis
from culsma.pipeline.ir_nodes import IRArg, IRProgram, IRProtocol

from .context import (
    BlockContext,
    CompileSession,
    _require_span,
    _protocol_tail_return,
    _validate_protocol_return_contract,
)
from .expressions import ExprCompiler
from .callable import CallableLowering
from .targets import TargetResolver
from .schedule import ScheduleEvaluator
from .statements import StatementCompiler


@dataclass(frozen=True)
class CompileResult:
    ir: IRProgram
    analysis: CompileAnalysis


def compile_ast(ast: Program) -> CompileResult:
    """Compile Program AST to Canonical IR plus sidecar analysis."""
    return IRCompiler(ast).compile_program(ast)


class IRCompiler:
    def __init__(self, ast: Program) -> None:
        self.session = CompileSession.from_program(ast)
        self.callable_lowering = CallableLowering(session=self.session)
        self.target_resolver = TargetResolver(session=self.session)
        self.schedule_evaluator = ScheduleEvaluator()
        self.expr_compiler = ExprCompiler(callable_lowering=self.callable_lowering)
        self.statement_compiler = StatementCompiler(
            session=self.session,
            expr_compiler=self.expr_compiler,
            callable_lowering=self.callable_lowering,
            target_resolver=self.target_resolver,
            schedule_evaluator=self.schedule_evaluator,
        )

    def compile_program(self, ast: Program) -> CompileResult:
        protocols = [
            self.compile_protocol(proto, proto_index=i)
            for i, proto in enumerate(ast.protocols)
        ]
        ir = IRProgram(protocols=protocols, span=ast.span)
        return CompileResult(
            ir=ir,
            analysis=self.session.analysis_builder.build(protocol_ids=[protocol.id for protocol in protocols]),
        )

    def compile_protocol(self, proto: ProtocolDecl, *, proto_index: int) -> IRProtocol:
        _require_span(proto, f"protocol[{proto_index}]")
        _validate_protocol_return_contract(proto)
        return_stmt = _protocol_tail_return(proto)
        proto_id = f"p{proto_index}"
        ctx = BlockContext(
            scope_id=proto_id,
            local_names={param.name for param in proto.params},
        )
        statements = self.statement_compiler.compile_list(proto.statements, ctx=ctx)
        return IRProtocol(
            id=proto_id,
            name=proto.name,
            params=[self.expr_compiler.compile_param(param) for param in proto.params],
            returns=list(proto.returns),
            return_value=(
                self.expr_compiler.compile(return_stmt.value)
                if return_stmt is not None and return_stmt.value is not None
                else None
            ),
            return_bindings=[
                IRArg(
                    name=binding.name,
                    value=self.expr_compiler.compile(binding.value),
                    span=binding.span,
                )
                for binding in (return_stmt.bindings if return_stmt is not None else [])
            ],
            statements=statements,
            span=proto.span,
        )
