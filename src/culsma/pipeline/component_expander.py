"""Expand callable LW component protocols into plain core AST."""

from __future__ import annotations

from typing import Iterable

from culsma.parser.ast_nodes import (
    Arg,
    AssignStatement,
    BinaryOp,
    BooleanLiteral,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStatement,
    Expression,
    GroupExpr,
    Identifier,
    IfStatement,
    IncludeStatement,
    IndexExpr,
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
    ReturnBinding,
    ReturnStatement,
    RepeatStatement,
    SelectorRegion,
    StepCall,
    StringLiteral,
    UnaryOp,
    WithConstraintStmt,
    WithEnvStmt,
)


def expand_component_calls(
    program: Program,
    *,
    external_protocols: Iterable[ProtocolDecl] = (),
) -> Program:
    """Rewrite protocol calls against injected external/user protocols into plain AST statements."""
    lookup = _build_component_lookup(program, external_protocols=external_protocols)
    protocols = [
        ProtocolDecl(
            name=protocol.name,
            module=protocol.module,
            params=list(protocol.params),
            returns=list(protocol.returns),
            statements=_expand_statement_list(protocol.statements, lookup=lookup, call_stack=[protocol.name], token_seed=protocol.name),
            span=protocol.span,
        )
        for protocol in program.protocols
    ]
    return Program(
        source_includes=list(program.source_includes),
        library_imports=list(program.library_imports),
        protocols=protocols,
        span=program.span,
    )


def _build_component_lookup(
    program: Program,
    *,
    external_protocols: Iterable[ProtocolDecl],
) -> dict[str, ProtocolDecl]:
    lookup = {protocol.name: protocol for protocol in external_protocols}
    lookup.update({protocol.name: protocol for protocol in program.protocols})
    return lookup


def _should_inline_protocol(protocol: ProtocolDecl, call_args: list[Arg]) -> bool:
    return True


def _expand_statement_list(
    statements: list[object],
    *,
    lookup: dict[str, ProtocolDecl],
    call_stack: list[str],
    token_seed: str,
) -> list[object]:
    expanded: list[object] = []
    for index, stmt in enumerate(statements):
        token = f"{token_seed}_s{index}"
        expanded.extend(
            _expand_statement(
                stmt,
                lookup=lookup,
                call_stack=call_stack,
                token_seed=token,
            )
        )
    return expanded


def _expand_statement(
    stmt: object,
    *,
    lookup: dict[str, ProtocolDecl],
    call_stack: list[str],
    token_seed: str,
) -> list[object]:
    if isinstance(stmt, LetStatement):
        if isinstance(stmt.value, CallExpr) and stmt.value.name in lookup and _should_inline_protocol(lookup[stmt.value.name], stmt.value.args):
            return _inline_component_call(
                protocol=lookup[stmt.value.name],
                call_args=stmt.value.args,
                result_name=stmt.name,
                lookup=lookup,
                call_stack=call_stack,
                token_seed=token_seed,
                call_span=stmt.span,
            )
        _assert_no_nested_component_calls(stmt.value, lookup, owner=f"let {stmt.name}")
        return [stmt]

    if isinstance(stmt, StepCall):
        if stmt.name in lookup and _should_inline_protocol(lookup[stmt.name], stmt.args):
            return _inline_component_call(
                protocol=lookup[stmt.name],
                call_args=stmt.args,
                result_name=None,
                lookup=lookup,
                call_stack=call_stack,
                token_seed=token_seed,
                call_span=stmt.span,
            )
        for arg in stmt.args:
            _assert_no_nested_component_calls(arg.value, lookup, owner=f"step {stmt.name}")
        return [stmt]

    if isinstance(stmt, AssignStatement):
        _assert_no_nested_component_calls(stmt.target, lookup, owner="assign target")
        _assert_no_nested_component_calls(stmt.value, lookup, owner="assign")
        return [stmt]

    if isinstance(stmt, ExprStatement):
        _assert_no_nested_component_calls(stmt.value, lookup, owner="expr statement")
        return [stmt]

    if isinstance(stmt, ReturnStatement):
        if stmt.value is not None:
            _assert_no_nested_component_calls(stmt.value, lookup, owner="return")
        for binding in stmt.bindings:
            _assert_no_nested_component_calls(binding.value, lookup, owner=f"return {binding.name}")
        return [stmt]

    if isinstance(stmt, WithEnvStmt):
        for arg in stmt.env_args:
            _assert_no_nested_component_calls(arg.value, lookup, owner="with env")
        return [
            WithEnvStmt(
                env_args=list(stmt.env_args),
                statements=_expand_statement_list(
                    stmt.statements,
                    lookup=lookup,
                    call_stack=call_stack,
                    token_seed=f"{token_seed}_env",
                ),
                span=stmt.span,
            )
        ]

    if isinstance(stmt, WithConstraintStmt):
        for arg in stmt.options:
            _assert_no_nested_component_calls(arg.value, lookup, owner="with constraint")
        return [
            WithConstraintStmt(
                requirements=list(stmt.requirements),
                options=list(stmt.options),
                statements=_expand_statement_list(
                    stmt.statements,
                    lookup=lookup,
                    call_stack=call_stack,
                    token_seed=f"{token_seed}_constraint",
                ),
                span=stmt.span,
            )
        ]

    if isinstance(stmt, MutationStmt):
        _assert_no_nested_component_calls(stmt.target, lookup, owner="mutation target")
        for source in stmt.sources:
            _assert_no_nested_component_calls(source, lookup, owner="mutation source")
        return [stmt]

    if isinstance(stmt, RepeatStatement):
        if stmt.times is not None:
            _assert_no_nested_component_calls(stmt.times, lookup, owner="repeat times")
        if stmt.iterable is not None:
            _assert_no_nested_component_calls(stmt.iterable, lookup, owner="repeat iterable")
        return [
            RepeatStatement(
                times=stmt.times,
                binding=stmt.binding,
                iterable=stmt.iterable,
                statements=_expand_statement_list(
                    stmt.statements,
                    lookup=lookup,
                    call_stack=call_stack,
                    token_seed=f"{token_seed}_repeat",
                ),
                span=stmt.span,
            )
        ]

    if isinstance(stmt, IfStatement):
        _assert_no_nested_component_calls(stmt.condition, lookup, owner="if condition")
        return [
            IfStatement(
                condition=stmt.condition,
                then_statements=_expand_statement_list(
                    stmt.then_statements,
                    lookup=lookup,
                    call_stack=call_stack,
                    token_seed=f"{token_seed}_then",
                ),
                else_statements=_expand_statement_list(
                    stmt.else_statements,
                    lookup=lookup,
                    call_stack=call_stack,
                    token_seed=f"{token_seed}_else",
                ),
                span=stmt.span,
            )
        ]

    if isinstance(stmt, (IncludeStatement, ProtocolRefStatement, BreakStmt, ContinueStmt)):
        return [stmt]

    raise TypeError(f"Unsupported AST statement type for component expansion: {type(stmt).__name__}")


def _inline_component_call(
    *,
    protocol: ProtocolDecl,
    call_args: list[Arg],
    result_name: str | None,
    lookup: dict[str, ProtocolDecl],
    call_stack: list[str],
    token_seed: str,
    call_span,
) -> list[object]:
    if protocol.name in call_stack:
        cycle = " -> ".join([*call_stack, protocol.name])
        raise ValueError(f"Component call cycle detected: {cycle}")

    body_statements, return_stmt = _split_component_body(protocol)
    if result_name is not None and return_stmt is None:
        raise ValueError(f"Component '{protocol.name}' does not define a return value")
    if result_name is not None and return_stmt is not None and return_stmt.bindings:
        if len(return_stmt.bindings) != 1 or len(protocol.returns) != 1:
            raise ValueError(
                f"Component '{protocol.name}' uses named multi-return and cannot be let-bound until bundle return semantics are implemented"
            )

    rename_map = _build_rename_map(protocol, token_seed=token_seed)
    direct_result_bind = False
    if (
        result_name is not None
        and return_stmt is not None
        and not return_stmt.bindings
        and isinstance(return_stmt.value, Identifier)
    ):
        returned_name = return_stmt.value.name
        if returned_name in rename_map:
            rename_map[returned_name] = result_name
            direct_result_bind = True
    bound_prefix = _bind_component_params(
        protocol=protocol,
        call_args=call_args,
        rename_map=rename_map,
        call_span=call_span,
    )
    renamed_body = [_rename_statement(stmt, rename_map) for stmt in body_statements]
    expanded = _expand_statement_list(
        [*bound_prefix, *renamed_body],
        lookup=lookup,
        call_stack=[*call_stack, protocol.name],
        token_seed=f"{token_seed}_{protocol.name}",
    )
    if result_name is None:
        return expanded

    if direct_result_bind:
        return expanded

    assert return_stmt is not None
    if return_stmt.bindings:
        renamed_return = _rename_expr(return_stmt.bindings[0].value, rename_map)
    else:
        assert return_stmt.value is not None
        renamed_return = _rename_expr(return_stmt.value, rename_map)
    final_bind = LetStatement(name=result_name, value=renamed_return, span=call_span)
    expanded.extend(
        _expand_statement_list(
            [final_bind],
            lookup=lookup,
            call_stack=[*call_stack, protocol.name],
            token_seed=f"{token_seed}_{protocol.name}_ret",
        )
    )
    return expanded


def _split_component_body(protocol: ProtocolDecl) -> tuple[list[object], ReturnStatement | None]:
    _ensure_no_nested_return(protocol.statements, protocol_name=protocol.name)
    if not protocol.statements:
        return [], None
    tail = protocol.statements[-1]
    if isinstance(tail, ReturnStatement):
        return list(protocol.statements[:-1]), tail
    for stmt in protocol.statements[:-1]:
        if isinstance(stmt, ReturnStatement):
            raise ValueError(f"Component '{protocol.name}' only supports tail return statements")
    return list(protocol.statements), None


def _ensure_no_nested_return(statements: list[object], *, protocol_name: str) -> None:
    for stmt in statements:
        nested: list[object] = []
        if isinstance(stmt, WithEnvStmt):
            nested = stmt.statements
        elif isinstance(stmt, RepeatStatement):
            nested = stmt.statements
        elif isinstance(stmt, IfStatement):
            nested = [*stmt.then_statements, *stmt.else_statements]
        if any(isinstance(item, ReturnStatement) for item in nested):
            raise ValueError(f"Component '{protocol_name}' only supports top-level tail return statements")
        if nested:
            _ensure_no_nested_return(nested, protocol_name=protocol_name)


def _build_rename_map(protocol: ProtocolDecl, *, token_seed: str) -> dict[str, str]:
    names = {param.name for param in protocol.params}
    names.update(_collect_declared_names(protocol.statements))
    return {name: f"__cmp_{token_seed}_{name}" for name in sorted(names)}


def _collect_declared_names(statements: list[object]) -> set[str]:
    names: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, LetStatement):
            names.add(stmt.name)
        elif isinstance(stmt, AssignStatement):
            if isinstance(stmt.target, Identifier):
                names.add(stmt.target.name)
        elif isinstance(stmt, RepeatStatement):
            if stmt.binding is not None:
                names.add(stmt.binding)
            names.update(_collect_declared_names(stmt.statements))
        elif isinstance(stmt, IfStatement):
            names.update(_collect_declared_names(stmt.then_statements))
            names.update(_collect_declared_names(stmt.else_statements))
        elif isinstance(stmt, WithEnvStmt):
            names.update(_collect_declared_names(stmt.statements))
        elif isinstance(stmt, WithConstraintStmt):
            names.update(_collect_declared_names(stmt.statements))
    return names


def _bind_component_params(
    *,
    protocol: ProtocolDecl,
    call_args: list[Arg],
    rename_map: dict[str, str],
    call_span,
) -> list[LetStatement]:
    seen: set[str] = set()
    provided: dict[str, Expression] = {}
    param_by_name = {param.name: param for param in protocol.params}
    for arg in call_args:
        if arg.name in seen:
            raise ValueError(f"Component '{protocol.name}' received duplicate argument '{arg.name}'")
        if arg.name not in param_by_name:
            raise ValueError(f"Component '{protocol.name}' does not accept argument '{arg.name}'")
        seen.add(arg.name)
        provided[arg.name] = arg.value

    prefix: list[LetStatement] = []
    for param in protocol.params:
        if param.name in provided:
            value = provided[param.name]
        elif param.default is not None:
            value = _rename_expr(param.default, rename_map)
        else:
            raise ValueError(f"Component '{protocol.name}' requires argument '{param.name}'")
        prefix.append(
            LetStatement(
                name=rename_map[param.name],
                value=value,
                span=call_span or param.span,
            )
        )
    return prefix


def _rename_statement(stmt: object, rename_map: dict[str, str]) -> object:
    if isinstance(stmt, LetStatement):
        return LetStatement(name=rename_map.get(stmt.name, stmt.name), value=_rename_expr(stmt.value, rename_map), span=stmt.span)
    if isinstance(stmt, ReturnStatement):
        return ReturnStatement(
            value=_rename_expr(stmt.value, rename_map) if stmt.value is not None else None,
            bindings=[
                ReturnBinding(name=binding.name, value=_rename_expr(binding.value, rename_map), span=binding.span)
                for binding in stmt.bindings
            ],
            span=stmt.span,
        )
    if isinstance(stmt, AssignStatement):
        return AssignStatement(target=_rename_expr(stmt.target, rename_map), value=_rename_expr(stmt.value, rename_map), span=stmt.span)
    if isinstance(stmt, ExprStatement):
        return ExprStatement(value=_rename_expr(stmt.value, rename_map), span=stmt.span)
    if isinstance(stmt, StepCall):
        return StepCall(
            name=stmt.name,
            args=[Arg(name=arg.name, value=_rename_expr(arg.value, rename_map), span=arg.span) for arg in stmt.args],
            span=stmt.span,
        )
    if isinstance(stmt, WithEnvStmt):
        return WithEnvStmt(
            env_args=[Arg(name=arg.name, value=_rename_expr(arg.value, rename_map), span=arg.span) for arg in stmt.env_args],
            statements=[_rename_statement(nested, rename_map) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, WithConstraintStmt):
        return WithConstraintStmt(
            requirements=list(stmt.requirements),
            options=[Arg(name=arg.name, value=_rename_expr(arg.value, rename_map), span=arg.span) for arg in stmt.options],
            statements=[_rename_statement(nested, rename_map) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, MutationStmt):
        return MutationStmt(
            target=_rename_expr(stmt.target, rename_map),
            sources=[_rename_expr(source, rename_map) for source in stmt.sources],
            span=stmt.span,
        )
    if isinstance(stmt, RepeatStatement):
        return RepeatStatement(
            times=_rename_expr(stmt.times, rename_map) if stmt.times is not None else None,
            binding=rename_map.get(stmt.binding, stmt.binding) if stmt.binding is not None else None,
            iterable=_rename_expr(stmt.iterable, rename_map) if stmt.iterable is not None else None,
            statements=[_rename_statement(nested, rename_map) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, IfStatement):
        return IfStatement(
            condition=_rename_expr(stmt.condition, rename_map),
            then_statements=[_rename_statement(nested, rename_map) for nested in stmt.then_statements],
            else_statements=[_rename_statement(nested, rename_map) for nested in stmt.else_statements],
            span=stmt.span,
        )
    if isinstance(stmt, (IncludeStatement, ProtocolRefStatement, BreakStmt, ContinueStmt)):
        return stmt
    raise TypeError(f"Unsupported AST statement for renaming: {type(stmt).__name__}")


def _rename_expr(expr: Expression, rename_map: dict[str, str]) -> Expression:
    if isinstance(expr, Identifier):
        return Identifier(name=rename_map.get(expr.name, expr.name), span=expr.span)
    if isinstance(expr, BinaryOp):
        return BinaryOp(op=expr.op, left=_rename_expr(expr.left, rename_map), right=_rename_expr(expr.right, rename_map), span=expr.span)
    if isinstance(expr, UnaryOp):
        return UnaryOp(op=expr.op, operand=_rename_expr(expr.operand, rename_map), span=expr.span)
    if isinstance(expr, ListLiteral):
        return ListLiteral(elements=[_rename_expr(item, rename_map) for item in expr.elements], span=expr.span)
    if isinstance(expr, GroupExpr):
        return GroupExpr(elements=[_rename_expr(item, rename_map) for item in expr.elements], span=expr.span)
    if isinstance(expr, CallExpr):
        return CallExpr(
            name=expr.name,
            args=[Arg(name=arg.name, value=_rename_expr(arg.value, rename_map), span=arg.span) for arg in expr.args],
            span=expr.span,
        )
    if isinstance(expr, PlateSelectorExpr):
        return PlateSelectorExpr(
            base=Identifier(name=rename_map.get(expr.base.name, expr.base.name), span=expr.base.span),
            regions=[SelectorRegion(start=region.start, end=region.end, span=region.span) for region in expr.regions],
            span=expr.span,
        )
    if isinstance(expr, IndexExpr):
        return IndexExpr(base=_rename_expr(expr.base, rename_map), index=_rename_expr(expr.index, rename_map), span=expr.span)
    if isinstance(expr, MemberExpr):
        return MemberExpr(base=_rename_expr(expr.base, rename_map), member=expr.member, span=expr.span)
    if isinstance(expr, MethodCallExpr):
        return MethodCallExpr(
            base=_rename_expr(expr.base, rename_map),
            method=expr.method,
            args=[_rename_expr(arg, rename_map) for arg in expr.args],
            span=expr.span,
        )
    if isinstance(expr, PairExpr):
        return PairExpr(left=_rename_expr(expr.left, rename_map), right=_rename_expr(expr.right, rename_map), span=expr.span)
    if isinstance(expr, (Quantity, StringLiteral, BooleanLiteral)):
        return expr
    raise TypeError(f"Unsupported AST expression for renaming: {type(expr).__name__}")


def _assert_no_nested_component_calls(expr: Expression, lookup: dict[str, ProtocolDecl], *, owner: str) -> None:
    if _contains_component_call(expr, lookup):
        raise ValueError(f"{owner} does not support nested component calls; hoist them into a let binding first")


def _contains_component_call(expr: Expression, lookup: dict[str, ProtocolDecl]) -> bool:
    if isinstance(expr, CallExpr):
        if expr.name in lookup:
            return True
        return any(_contains_component_call(arg.value, lookup) for arg in expr.args)
    if isinstance(expr, BinaryOp):
        return _contains_component_call(expr.left, lookup) or _contains_component_call(expr.right, lookup)
    if isinstance(expr, UnaryOp):
        return _contains_component_call(expr.operand, lookup)
    if isinstance(expr, ListLiteral):
        return any(_contains_component_call(item, lookup) for item in expr.elements)
    if isinstance(expr, GroupExpr):
        return any(_contains_component_call(item, lookup) for item in expr.elements)
    if isinstance(expr, PlateSelectorExpr):
        return False
    if isinstance(expr, IndexExpr):
        return _contains_component_call(expr.base, lookup) or _contains_component_call(expr.index, lookup)
    if isinstance(expr, MemberExpr):
        return _contains_component_call(expr.base, lookup)
    if isinstance(expr, MethodCallExpr):
        return _contains_component_call(expr.base, lookup) or any(_contains_component_call(arg, lookup) for arg in expr.args)
    if isinstance(expr, PairExpr):
        return _contains_component_call(expr.left, lookup) or _contains_component_call(expr.right, lookup)
    return False
