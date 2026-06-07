from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from culsma.common.source import Span
from culsma.parser.ast_nodes import (
    Arg,
    AssignStatement,
    BinaryOp,
    BooleanLiteral,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStatement,
    GroupExpr,
    Identifier,
    IfStatement,
    IncludeStatement,
    IndexExpr,
    LibraryImportDecl,
    LetStatement,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    MutationStmt,
    PairExpr,
    ParamDecl,
    PlateSelectorExpr,
    Program,
    ProtocolDecl,
    ProtocolRefStatement,
    Quantity,
    RecordLiteral,
    RepeatStatement,
    ReturnBinding,
    ReturnStatement,
    SelectorRegion,
    SourceIncludeDecl,
    StepCall,
    StringLiteral,
    UnaryOp,
    WithConstraintStmt,
    WithEnvStmt,
)

_QUANTITY_RE = re.compile(
    r"^(\d+(?:\.\d+)?)"
    r"(ng_per_uL|ug_per_mL|day|sec|rpm|rcf|pct|min|mL|ml|uL|ul|mM|uM|nM|nm|mW|mV|mg|ug|kg|um|hr|Hz|xg|ms|L|g|s|h|C|K|M|W|V|X|%)?$"
)


class CommonHelpers:
    @staticmethod
    def span_from_meta(meta: Any) -> Span | None:
        line = getattr(meta, "line", None)
        column = getattr(meta, "column", None)
        start_pos = getattr(meta, "start_pos", None)
        end_pos = getattr(meta, "end_pos", None)
        if line is None or column is None:
            return None
        if start_pos is None or end_pos is None:
            return None
        return Span(line=int(line), col=int(column), start=int(start_pos), end=int(end_pos))

    @staticmethod
    def decode_string_token(token: Any) -> str:
        decoded = ast.literal_eval(str(token))
        if not isinstance(decoded, str):
            raise ValueError(f"Expected string token, got {token!r}")
        return decoded

    @staticmethod
    def decode_quantity(token: Any, span: Span | None) -> Quantity:
        token_str = str(token)
        match = _QUANTITY_RE.match(token_str)
        if not match:
            raise ValueError(f"Invalid QUANTITY token: {token_str!r}")
        return Quantity(value=float(match.group(1)), unit=match.group(2), span=span)

    @staticmethod
    def decode_boolean(token: Any, span: Span | None) -> BooleanLiteral:
        return BooleanLiteral(value=str(token) == "true", span=span)

    @staticmethod
    @staticmethod
    def decode_selector_region(start_token: Any, end_token: Any | None, span: Span | None) -> SelectorRegion:
        return SelectorRegion(
            start=str(start_token),
            end=str(end_token) if end_token is not None else None,
            span=span,
        )


class ParseRuleContext:
    def __init__(self, helpers: CommonHelpers | None = None) -> None:
        self.helpers = helpers or CommonHelpers()

    def span_from_meta(self, meta: Any) -> Span | None:
        return self.helpers.span_from_meta(meta)

    def decode_string_token(self, token: Any) -> str:
        return self.helpers.decode_string_token(token)

    def decode_quantity(self, token: Any, meta: Any) -> Quantity:
        return self.helpers.decode_quantity(token, self.span_from_meta(meta))

    def decode_boolean(self, token: Any, meta: Any) -> BooleanLiteral:
        return self.helpers.decode_boolean(token, self.span_from_meta(meta))

    def decode_selector_region(self, start_token: Any, end_token: Any | None, meta: Any) -> SelectorRegion:
        return self.helpers.decode_selector_region(start_token, end_token, self.span_from_meta(meta))


@dataclass
class ParseRuleState:
    span: Span | None = None


class BaseParseRuleHandler:
    def handle(self, meta: Any, items: list[Any], ctx: ParseRuleContext) -> Any:
        state = self.prepare(meta, items, ctx)
        state.span = self.read_span(meta, ctx)
        self.use_children(meta, items, ctx, state)
        self.normalize_surface(meta, items, ctx, state)
        return self.construct_ast(meta, items, ctx, state)

    def prepare(self, meta: Any, items: list[Any], ctx: ParseRuleContext) -> ParseRuleState:
        del meta, items, ctx
        return ParseRuleState()

    def read_span(self, meta: Any, ctx: ParseRuleContext) -> Span | None:
        return ctx.span_from_meta(meta)

    def use_children(
        self,
        meta: Any,
        items: list[Any],
        ctx: ParseRuleContext,
        state: ParseRuleState,
    ) -> None:
        del meta, items, ctx, state

    def normalize_surface(
        self,
        meta: Any,
        items: list[Any],
        ctx: ParseRuleContext,
        state: ParseRuleState,
    ) -> None:
        del meta, items, ctx, state

    def construct_ast(
        self,
        meta: Any,
        items: list[Any],
        ctx: ParseRuleContext,
        state: ParseRuleState,
    ) -> Any:
        raise NotImplementedError(type(self).__name__)


class TopLevelRuleHandler(BaseParseRuleHandler):
    pass


class StatementRuleHandler(BaseParseRuleHandler):
    pass


class ExpressionRuleHandler(BaseParseRuleHandler):
    pass


class SurfaceRuleHandler(BaseParseRuleHandler):
    pass


class ListRuleHandler(BaseParseRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> list[Any]:
        del meta, ctx, state
        return list(items)


class FirstItemRuleHandler(BaseParseRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Any:
        del meta, ctx, state
        return items[0]


class EmptyOrFirstRuleHandler(BaseParseRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Any:
        del meta, ctx, state
        return items[0] if items else []


class StringListRuleHandler(BaseParseRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> list[str]:
        del meta, ctx, state
        return [str(item) for item in items]


class StartHandler(TopLevelRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Program:
        del meta, ctx
        source_includes: list[SourceIncludeDecl] = []
        library_imports: list[LibraryImportDecl] = []
        protocols: list[ProtocolDecl] = []
        for item in items:
            if isinstance(item, SourceIncludeDecl):
                source_includes.append(item)
                continue
            if isinstance(item, LibraryImportDecl):
                library_imports.append(item)
                continue
            if isinstance(item, ProtocolDecl):
                protocols.append(item)
                continue
            raise TypeError(f"Unexpected top-level node type: {type(item).__name__}")
        return Program(
            source_includes=source_includes,
            library_imports=library_imports,
            protocols=protocols,
            span=state.span,
        )


class SourceIncludeDeclHandler(TopLevelRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> SourceIncludeDecl:
        del meta
        return SourceIncludeDecl(path=ctx.decode_string_token(items[0]), span=state.span)


class LibraryImportDeclHandler(TopLevelRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> LibraryImportDecl:
        del meta, ctx
        return LibraryImportDecl(name=str(items[0]), span=state.span)


class ProtocolDeclHandler(TopLevelRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> ProtocolDecl:
        del meta, ctx
        name = str(items[0])
        remaining = list(items[1:])
        params: list[ParamDecl] = []
        returns: list[str] = []
        if remaining and isinstance(remaining[0], list) and (not remaining[0] or isinstance(remaining[0][0], ParamDecl)):
            params = remaining.pop(0)
        if remaining and isinstance(remaining[0], list) and (not remaining[0] or isinstance(remaining[0][0], str)):
            returns = remaining.pop(0)
        return ProtocolDecl(name=name, params=params, returns=returns, statements=remaining, span=state.span)


class ParamDeclHandler(TopLevelRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> ParamDecl:
        del meta, ctx
        default = items[1] if len(items) > 1 else None
        return ParamDecl(name=str(items[0]), default=default, span=state.span)


class IncludeStmtHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> IncludeStatement:
        del meta, ctx
        return IncludeStatement(name=str(items[0]), span=state.span)


class LetStatementHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> LetStatement:
        del meta, ctx
        return LetStatement(name=str(items[0]), value=items[1], span=state.span)


class ReturnStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> ReturnStatement:
        del meta, ctx
        return ReturnStatement(value=items[0], bindings=[], span=state.span)


class NamedReturnBindingHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> ReturnBinding:
        del meta, ctx
        return ReturnBinding(name=str(items[0]), value=items[1], span=state.span)


class NamedReturnStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> ReturnStatement:
        del meta, ctx
        return ReturnStatement(value=None, bindings=list(items[0]), span=state.span)


class AssignIdentifierStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> AssignStatement:
        del meta, ctx
        target = Identifier(name=str(items[0]), span=state.span)
        return AssignStatement(target=target, value=items[1], span=state.span)


class AssignMemberStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> AssignStatement:
        del meta, ctx
        target = MemberExpr(base=items[0], member=str(items[1]), span=state.span)
        return AssignStatement(target=target, value=items[2], span=state.span)


class CallStatementHandler(SurfaceRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Any:
        del meta, ctx
        base = items[0]
        method = str(items[1])
        raw_args = items[2] if len(items) > 2 else []
        if hasattr(base, "name") and isinstance(getattr(base, "name"), str) and method and method[0].isupper():
            normalized_args: list[Arg] = []
            for idx, arg in enumerate(raw_args):
                if isinstance(arg, Arg):
                    normalized_args.append(arg)
                else:
                    normalized_args.append(Arg(name=f"arg{idx}", value=arg, span=getattr(arg, "span", None)))
            return ProtocolRefStatement(module=base.name, protocol=method, args=normalized_args, span=state.span)
        if any(isinstance(arg, Arg) for arg in raw_args):
            raise ValueError("method call statements only accept positional args unless parsed as Module.Protocol(...)")
        return ExprStatement(value=MethodCallExpr(base=base, method=method, args=list(raw_args), span=state.span), span=state.span)


class MethodCallStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> ExprStatement:
        del meta, ctx
        args = items[2] if len(items) > 2 else []
        return ExprStatement(value=MethodCallExpr(base=items[0], method=str(items[1]), args=args, span=state.span), span=state.span)


class StepCallHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> StepCall:
        del meta, ctx
        name = str(items[0])
        raw_args = items[1] if len(items) > 1 else []
        args: list[Arg] = []
        for index, raw_arg in enumerate(raw_args):
            if isinstance(raw_arg, Arg):
                args.append(raw_arg)
                continue
            if name != "hold":
                raise ValueError("step calls only accept named args; hold(...) is the only positional step form")
            args.append(
                Arg(
                    name="target" if index == 0 else f"arg{index}",
                    value=raw_arg,
                    span=getattr(raw_arg, "span", state.span),
                )
            )
        return StepCall(name=name, args=args, span=state.span)


class EmptyArgBlockHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> list[Any]:
        del meta, ctx, state
        return items[0] if items else []


class ConstraintNameHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> str:
        del meta, ctx, state
        return str(items[0])


def _split_constraint_items(raw_items: list[Any]) -> tuple[list[str], list[Arg]]:
    requirements = [item for item in raw_items if isinstance(item, str)]
    options = [item for item in raw_items if isinstance(item, Arg)]
    return requirements, options


class WithEnvStmtHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> WithEnvStmt:
        del meta, ctx
        return WithEnvStmt(env_args=items[0], statements=list(items[1:]), span=state.span)


class WithConstraintStmtHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> WithConstraintStmt:
        del meta, ctx
        requirements, options = _split_constraint_items(items[0])
        return WithConstraintStmt(requirements=requirements, options=options, statements=list(items[1:]), span=state.span)


class ConstrainedSimpleStatementHandler(SurfaceRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> WithConstraintStmt:
        del meta, ctx
        requirements, options = _split_constraint_items(items[1])
        return WithConstraintStmt(requirements=requirements, options=options, statements=[items[0]], span=state.span)


class MutationStmtHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> MutationStmt:
        del meta, ctx
        return MutationStmt(target=items[0], sources=items[2], span=state.span)


class BreakStmtHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> BreakStmt:
        del meta, items, ctx
        return BreakStmt(span=state.span)


class ContinueStmtHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> ContinueStmt:
        del meta, items, ctx
        return ContinueStmt(span=state.span)


class RepeatBindingHeaderHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> tuple[str, str, Any]:
        del meta, ctx, state
        return ("binding", str(items[0]), items[1])


class RepeatTimesHeaderHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> tuple[str, Any]:
        del meta, ctx, state
        return ("times", items[0])


class RepeatStatementHandler(StatementRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> RepeatStatement:
        del meta, ctx
        header = items[0]
        statements = list(items[1:])
        if header[0] == "binding":
            return RepeatStatement(binding=header[1], iterable=header[2], statements=statements, span=state.span)
        return RepeatStatement(times=header[1], statements=statements, span=state.span)


class IfStatementHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> IfStatement:
        del meta, ctx
        condition = items[0]
        body_items = list(items[1:])
        else_statements: list[Any] = []
        if body_items and isinstance(body_items[-1], list):
            else_statements = body_items.pop()
        return IfStatement(condition=condition, then_statements=body_items, else_statements=else_statements, span=state.span)


class ArgHandler(StatementRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Arg:
        del meta, ctx
        return Arg(name=str(items[0]), value=items[1], span=state.span)


@dataclass
class BinaryOpHandler(ExpressionRuleHandler):
    op: str

    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> BinaryOp:
        del meta, ctx
        return BinaryOp(op=self.op, left=items[0], right=items[1], span=state.span)


class ComparisonHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> BinaryOp:
        del meta, ctx
        left, op_token, right = items
        return BinaryOp(op=str(op_token), left=left, right=right, span=state.span)


class NegOpHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> UnaryOp:
        del meta, ctx
        return UnaryOp(op="-", operand=items[0], span=state.span)


class QuantityHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Quantity:
        del state
        return ctx.decode_quantity(items[0], meta)


class StringLiteralHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> StringLiteral:
        del meta
        return StringLiteral(value=ctx.decode_string_token(items[0]), span=state.span)


class BooleanLiteralHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> BooleanLiteral:
        del state
        return ctx.decode_boolean(items[0], meta)


class IdentifierRefHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> Identifier:
        del meta, ctx
        return Identifier(name=str(items[0]), span=state.span)


class ListLiteralHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> ListLiteral:
        del meta, ctx
        return ListLiteral(elements=list(items), span=state.span)


class RecordKeyIdentifierHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> str:
        del meta, ctx, state
        return str(items[0])


class RecordKeyStringHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> str:
        del meta, state
        return ctx.decode_string_token(items[0])


class RecordItemHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> tuple[str, Any]:
        del meta, ctx, state
        return str(items[0]), items[1]


class RecordLiteralHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> RecordLiteral:
        del meta, ctx
        return RecordLiteral(entries=dict(items), span=state.span)


class GroupExprHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> GroupExpr:
        del meta, ctx
        return GroupExpr(elements=list(items), span=state.span)


class SelectorRegionHandler(ExpressionRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> SelectorRegion:
        del state
        end_token = items[1] if len(items) > 1 else None
        return ctx.decode_selector_region(items[0], end_token, meta)


class PlateSelectorExprHandler(ExpressionRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> PlateSelectorExpr:
        del meta, ctx
        base = items[0]
        if not isinstance(base, Identifier):
            raise ValueError("plate selector base must be an identifier")
        return PlateSelectorExpr(
            base=base,
            regions=list(items[1:]),
            span=state.span,
        )


class CallExprHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> CallExpr:
        del meta, ctx
        args = items[1] if len(items) > 1 else []
        return CallExpr(name=str(items[0]), args=args, span=state.span)


class MarkersExprHandler(SurfaceRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> CallExpr:
        del meta, ctx
        return CallExpr(name="markers", args=[Arg(name="items", value=items[0], span=state.span)], span=state.span)


class IndexExprHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> IndexExpr:
        del meta, ctx
        return IndexExpr(base=items[0], index=items[1], span=state.span)


class MemberExprHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> MemberExpr:
        del meta, ctx
        base = items[0]
        if not hasattr(base, "span"):
            base = Identifier(name=str(base), span=state.span)
        return MemberExpr(base=base, member=str(items[1]), span=state.span)


class MethodCallExprHandler(ExpressionRuleHandler):
    def construct_ast(
        self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState
    ) -> MethodCallExpr:
        del meta, ctx
        args = items[2] if len(items) > 2 else []
        return MethodCallExpr(base=items[0], method=str(items[1]), args=args, span=state.span)


class PairExprHandler(ExpressionRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> PairExpr:
        del meta, ctx
        return PairExpr(left=items[0], right=items[1], span=state.span)


class MutationSeriesExprHandler(SurfaceRuleHandler):
    def construct_ast(self, meta: Any, items: list[Any], ctx: ParseRuleContext, state: ParseRuleState) -> CallExpr:
        del meta, ctx
        return CallExpr(
            name="series",
            args=[
                Arg(name="source", value=items[0], span=state.span),
                Arg(name="values", value=items[1], span=state.span),
            ],
            span=state.span,
        )


class ParseRuleDispatcher:
    def __init__(self, handlers: dict[str, BaseParseRuleHandler]) -> None:
        self._handlers = handlers

    def handler_for(self, rule_name: str) -> BaseParseRuleHandler:
        handler = self._handlers.get(rule_name)
        if handler is None:
            raise AttributeError(f"No parse rule handler registered for {rule_name!r}")
        return handler

    def dispatch(self, rule_name: str, meta: Any, items: list[Any], ctx: ParseRuleContext) -> Any:
        return self.handler_for(rule_name).handle(meta, items, ctx)


def create_parse_rule_dispatcher() -> ParseRuleDispatcher:
    list_handler = ListRuleHandler()
    first_item_handler = FirstItemRuleHandler()
    empty_or_first_handler = EmptyOrFirstRuleHandler()
    return ParseRuleDispatcher(
        {
            "start": StartHandler(),
            "source_include_decl": SourceIncludeDeclHandler(),
            "library_import_decl": LibraryImportDeclHandler(),
            "protocol_decl": ProtocolDeclHandler(),
            "param_decl_list": list_handler,
            "param_decl": ParamDeclHandler(),
            "returns_decl": empty_or_first_handler,
            "return_name_list": StringListRuleHandler(),
            "statement": first_item_handler,
            "include_stmt": IncludeStmtHandler(),
            "let_statement": LetStatementHandler(),
            "return_statement": ReturnStatementHandler(),
            "named_return_binding": NamedReturnBindingHandler(),
            "named_return_binding_list": list_handler,
            "named_return_statement": NamedReturnStatementHandler(),
            "assign_identifier_statement": AssignIdentifierStatementHandler(),
            "assign_member_statement": AssignMemberStatementHandler(),
            "call_statement_arg_list": list_handler,
            "call_statement": CallStatementHandler(),
            "method_call_statement": MethodCallStatementHandler(),
            "step_call": StepCallHandler(),
            "step_arg_list": list_handler,
            "env_arg_block": EmptyArgBlockHandler(),
            "constraint_item_block": EmptyArgBlockHandler(),
            "constraint_item_list": list_handler,
            "constraint_name": ConstraintNameHandler(),
            "mutation_source_list": list_handler,
            "with_env_stmt": WithEnvStmtHandler(),
            "with_constraint_stmt": WithConstraintStmtHandler(),
            "constrained_simple_statement": ConstrainedSimpleStatementHandler(),
            "mutation_stmt": MutationStmtHandler(),
            "break_stmt": BreakStmtHandler(),
            "continue_stmt": ContinueStmtHandler(),
            "repeat_binding_header": RepeatBindingHeaderHandler(),
            "repeat_times_header": RepeatTimesHeaderHandler(),
            "repeat_statement": RepeatStatementHandler(),
            "else_clause": list_handler,
            "if_statement": IfStatementHandler(),
            "arg_list": list_handler,
            "arg": ArgHandler(),
            "or_op": BinaryOpHandler("or"),
            "and_op": BinaryOpHandler("and"),
            "comparison": ComparisonHandler(),
            "add_op": BinaryOpHandler("+"),
            "sub_op": BinaryOpHandler("-"),
            "mul_op": BinaryOpHandler("*"),
            "div_op": BinaryOpHandler("/"),
            "neg_op": NegOpHandler(),
            "quantity": QuantityHandler(),
            "string_literal": StringLiteralHandler(),
            "boolean_literal": BooleanLiteralHandler(),
            "identifier_ref": IdentifierRefHandler(),
            "list_literal": ListLiteralHandler(),
            "record_key_identifier": RecordKeyIdentifierHandler(),
            "record_key_string": RecordKeyStringHandler(),
            "record_item": RecordItemHandler(),
            "record_literal": RecordLiteralHandler(),
            "group_expr": GroupExprHandler(),
            "selector_region": SelectorRegionHandler(),
            "plate_selector_expr": PlateSelectorExprHandler(),
            "call_expr": CallExprHandler(),
            "method_call_arg_list": list_handler,
            "markers_expr": MarkersExprHandler(),
            "index_expr": IndexExprHandler(),
            "member_expr": MemberExprHandler(),
            "method_call_expr": MethodCallExprHandler(),
            "pair_expr": PairExprHandler(),
            "mutation_series_expr": MutationSeriesExprHandler(),
        }
    )
