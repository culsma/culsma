"""Program-level IR compiler orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from culsma.parser.ast_nodes import Expression, Program, ProtocolDecl
from culsma.pipeline.analysis import CompileAnalysis
from culsma.pipeline.ir_nodes import IRArg, IRLet, IRProgram, IRProtocol

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
from .static_control import StaticControlClassifier
from .repeat_control import RepeatControlLowerer
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
        self.static_control_classifier = StaticControlClassifier()
        self.repeat_control_lowerer = RepeatControlLowerer()
        self.expr_compiler = ExprCompiler(callable_lowering=self.callable_lowering)
        self.statement_compiler = StatementCompiler(
            session=self.session,
            expr_compiler=self.expr_compiler,
            callable_lowering=self.callable_lowering,
            target_resolver=self.target_resolver,
            schedule_evaluator=self.schedule_evaluator,
            static_control_classifier=self.static_control_classifier,
            repeat_control_lowerer=self.repeat_control_lowerer,
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
        param_names = {param.name for param in proto.params}
        ctx = BlockContext(
            scope_id=proto_id,
            local_names=set(param_names),
            param_names=param_names,
        )
        statements = self.statement_compiler.compile_list(proto.statements, ctx=ctx)
        return_prefix: list[IRLet] = []
        return_value: Expression | None = None
        if return_stmt is not None and return_stmt.value is not None:
            prefix, return_value = self._normalize_return_expr(
                return_stmt.value,
                stmt_id=f"{proto_id}.return",
                ctx=ctx,
            )
            return_prefix.extend(prefix)
        return_bindings: list[IRArg] = []
        return_binding_asts = return_stmt.bindings if return_stmt is not None else []
        for binding in return_binding_asts:
            prefix, normalized_value = self._normalize_return_expr(
                binding.value,
                stmt_id=f"{proto_id}.return.{binding.name}",
                ctx=ctx,
            )
            return_prefix.extend(prefix)
            return_bindings.append(
                IRArg(
                    name=binding.name,
                    value=self.expr_compiler.compile(normalized_value),
                    span=binding.span,
                )
            )
        if return_prefix:
            self.session.analysis_builder.record_statement_effects(
                protocol_id=proto_id,
                statements=return_prefix,
                protocols_by_name=self.session.protocol_id_by_name,
                collect_runtime_exports=True,
                expr_bindings=ctx.ir_expr_bindings,
                env=ctx.ir_const_env,
            )
            statements = [*statements, *return_prefix]
        return IRProtocol(
            id=proto_id,
            name=proto.name,
            params=[self.expr_compiler.compile_param(param) for param in proto.params],
            returns=list(proto.returns),
            return_value=(
                self.expr_compiler.compile(return_value)
                if return_value is not None
                else None
            ),
            return_bindings=return_bindings,
            statements=statements,
            span=proto.span,
        )

    def _normalize_return_expr(
        self,
        expr: Expression,
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], Expression]:
        prefix, normalized = self.target_resolver.normalize_group_like_expr(
            expr,
            stmt_id=stmt_id,
            ctx=ctx,
        )
        return prefix, normalized if normalized is not None else expr
