"""Program-level IR compiler orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from culsma.parser.ast_nodes import Expression, Program, ProtocolDecl, ReturnStatement, Statement
from culsma.pipeline.analysis import CompileAnalysis
from culsma.pipeline.ir_nodes import IRArg, IRLet, IRProgram, IRProtocol, IRScriptEntry
from culsma.pipeline.scope import ScopeAnalyzer

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
        script_entry = self.compile_script_entry(ast) if ast.statements else None
        user_protocols = [
            self.compile_protocol(proto, proto_index=i)
            for i, proto in enumerate(ast.protocols)
        ]
        ir = IRProgram(protocols=user_protocols, script_entry=script_entry, span=ast.span)
        scope = ScopeAnalyzer().analyze(ir)
        analysis_ids = [protocol.id for protocol in user_protocols]
        if script_entry is not None:
            analysis_ids.append(script_entry.id)
        return CompileResult(
            ir=ir,
            analysis=self.session.analysis_builder.build(
                protocol_ids=analysis_ids,
                scope=scope,
            ),
        )

    def compile_script_entry(self, ast: Program) -> IRScriptEntry:
        script_id = "entry"
        return_stmt = self.script_tail_return(ast.statements)
        ScopeAnalyzer().validate_unique_source_local_names(
            ast.statements,
            protocol_name="entry source",
        )
        ctx = BlockContext(
            scope_id=script_id,
            local_names=set(),
            param_names=set(),
        )
        statements = self.statement_compiler.compile_list(ast.statements, ctx=ctx)
        return_prefix, return_value, return_bindings, returns = self.compile_return(
            return_stmt=return_stmt,
            scope_id=script_id,
            ctx=ctx,
        )
        if return_prefix:
            self.session.analysis_builder.record_statement_effects(
                protocol_id=script_id,
                statements=return_prefix,
                protocols_by_name=self.session.protocol_id_by_name,
                collect_runtime_exports=True,
                expr_bindings=ctx.ir_expr_bindings,
                env=ctx.ir_const_env,
            )
            statements = [*statements, *return_prefix]
        return IRScriptEntry(
            id=script_id,
            statements=statements,
            returns=returns,
            return_value=(
                self.expr_compiler.compile(return_value)
                if return_value is not None
                else None
            ),
            return_bindings=return_bindings,
            source_paths=tuple(ast.entry_source_paths),
            span=ast.span or getattr(ast.statements[0], "span", None),
        )

    def compile_protocol(self, proto: ProtocolDecl, *, proto_index: int, proto_id: str | None = None) -> IRProtocol:
        _require_span(proto, f"protocol[{proto_index}]")
        _validate_protocol_return_contract(proto)
        return_stmt = _protocol_tail_return(proto)
        proto_id = proto_id or f"p{proto_index}"
        param_names = {param.name for param in proto.params}
        ScopeAnalyzer().validate_unique_source_local_names(
            proto.statements,
            reserved_names=param_names,
            protocol_name=proto.name,
        )
        ctx = BlockContext(
            scope_id=proto_id,
            local_names=set(param_names),
            param_names=param_names,
        )
        statements = self.statement_compiler.compile_list(proto.statements, ctx=ctx)
        return_prefix, return_value, return_bindings, _returns = self.compile_return(
            return_stmt=return_stmt,
            scope_id=proto_id,
            ctx=ctx,
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
            module=proto.module,
            source_path=proto.source_path,
            source_role=proto.source_role,
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

    def script_tail_return(self, statements: list[Statement]) -> ReturnStatement | None:
        tail_return: ReturnStatement | None = None
        for idx, stmt in enumerate(statements):
            if isinstance(stmt, ReturnStatement):
                if idx != len(statements) - 1:
                    raise ValueError("Entry source only supports top-level tail return statements")
                tail_return = stmt
        if tail_return is None:
            return None
        binding_names = [binding.name for binding in tail_return.bindings]
        if len(binding_names) != len(set(binding_names)):
            raise ValueError("Entry source return statement declares duplicate binding names")
        return tail_return

    def compile_return(
        self,
        *,
        return_stmt: ReturnStatement | None,
        scope_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], Expression | None, list[IRArg], list[str]]:
        return_prefix: list[IRLet] = []
        return_value: Expression | None = None
        if return_stmt is not None and return_stmt.value is not None:
            prefix, return_value = self._normalize_return_expr(
                return_stmt.value,
                stmt_id=f"{scope_id}.return",
                ctx=ctx,
            )
            return_prefix.extend(prefix)
        return_bindings: list[IRArg] = []
        returns: list[str] = []
        return_binding_asts = return_stmt.bindings if return_stmt is not None else []
        for binding in return_binding_asts:
            returns.append(binding.name)
            prefix, normalized_value = self._normalize_return_expr(
                binding.value,
                stmt_id=f"{scope_id}.return.{binding.name}",
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
        return return_prefix, return_value, return_bindings, returns

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
