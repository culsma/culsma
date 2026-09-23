"""Environment and mutation target expansion helpers."""

from __future__ import annotations

from culsma.domains.labware import PLATE_DIMENSIONS, PLATE_DEFAULT_WELL_CAPACITY, selector_positions

from dataclasses import dataclass

from culsma.parser.ast_nodes import (
    AssignStatement,
    Arg,
    CallExpr,
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
    MutationStmt,
    PairExpr,
    PlateSelectorExpr,
    ProtocolDecl,
    Quantity,
    RepeatStatement,
    Statement,
    StepCall,
    StringLiteral,
    WithConstraintStmt,
    WithEnvStmt,
)
from culsma.pipeline.ir_nodes import IRLet, IRPlateWellRef, IRIdentifier
from culsma.pipeline.container_views import classify_container_target_view, is_container_target_view_namespace_path

from .context import BlockContext, CompileSession, _CompilerState

# Compatibility views retain historical compiler lookup names.
_PLATE_FORMAT_DIMENSIONS = {member.value: dimensions for member, dimensions in PLATE_DIMENSIONS.items()}
_PLATE_FORMAT_DEFAULT_WELL_CAPACITY = {member.value: capacity for member, capacity in PLATE_DEFAULT_WELL_CAPACITY.items()}


@dataclass(frozen=True)
class EnvHoldMarkerSplit:
    hold_targets: list[Expression]
    executable_statements: list[Statement]
    has_invalid_nested_hold: bool

    @property
    def has_hold_targets(self) -> bool:
        return bool(self.hold_targets)

    @property
    def is_hold_only(self) -> bool:
        return bool(self.hold_targets) and not self.executable_statements


class TargetResolver:
    def __init__(self, *, session: CompileSession) -> None:
        self.session = session

    def assignment_target_root_name(self, expr: Expression) -> str | None:
        return _assignment_target_root_name(expr)

    def expand_env_targets(
        self,
        targets: list[Expression],
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], list[Expression]]:
        return _expand_env_targets(
            targets,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            state=self.session.state,
        )

    def infer_env_targets_from_source_statements(
        self,
        statements: list[Statement],
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], list[Expression]]:
        return _infer_env_targets_from_source_statements(
            statements,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            protocol_lookup=self.session.protocol_lookup,
            state=self.session.state,
        )

    def expand_mutation_targets(
        self,
        target: Expression,
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], list[Expression]]:
        return _expand_mutation_targets(
            target,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            state=self.session.state,
        )

    def expand_mutation_sources(
        self,
        sources: list[Expression],
        *,
        target: Expression,
        flattened_targets: list[Expression],
        ctx: BlockContext,
    ) -> list[list[Expression]]:
        return _expand_mutation_sources(
            sources,
            target=target,
            flattened_targets=flattened_targets,
            let_bindings=ctx.let_bindings,
        )

    def normalize_group_like_expr(
        self,
        expr: Expression,
        *,
        stmt_id: str,
        ctx: BlockContext,
    ) -> tuple[list[IRLet], Expression | None]:
        if not _is_group_like_ast(expr, ctx.let_bindings):
            return [], None
        prefix, members = _expand_group_like_target_expr(
            expr,
            stmt_id=stmt_id,
            let_bindings=ctx.let_bindings,
            state=self.session.state,
        )
        return prefix, GroupExpr(elements=members, span=expr.span)


def _assignment_target_root_name(expr: Expression) -> str | None:
    current = expr
    while isinstance(current, MemberExpr):
        current = current.base
    if isinstance(current, Identifier):
        return current.name
    return None


def _find_named_arg(args: list[Arg], name: str) -> Arg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def _expand_env_targets(
    targets: list[Expression],
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state: _CompilerState,
) -> tuple[list[IRLet], list[Expression]]:
    prefix: list[IRLet] = []
    flattened: list[Expression] = []
    seen: set[str] = set()
    for target in targets:
        target_prefix, members = _expand_group_like_target_expr(
            target,
            stmt_id=stmt_id,
            let_bindings=let_bindings,
            state=state,
        )
        prefix.extend(target_prefix)
        for member in members:
            key = _expr_identity_key(member)
            if key in seen:
                continue
            seen.add(key)
            flattened.append(member)
    return prefix, flattened


def _infer_env_targets_from_source_statements(
    statements: list[Statement],
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    protocol_lookup: dict[str, ProtocolDecl],
    state: _CompilerState,
) -> tuple[list[IRLet], list[Expression]]:
    collected: list[Expression] = []
    for stmt in statements:
        collected.extend(
            _collect_env_target_exprs_from_statement(
                stmt,
                let_bindings=let_bindings,
                protocol_lookup=protocol_lookup,
                visited_protocols=set(),
            )
        )
    return _expand_env_targets(
        collected,
        stmt_id=stmt_id,
        let_bindings=let_bindings,
        state=state,
    )


def _collect_env_target_exprs_from_statement(
    stmt: Statement,
    *,
    let_bindings: dict[str, Expression],
    protocol_lookup: dict[str, ProtocolDecl],
    visited_protocols: set[str],
) -> list[Expression]:
    if isinstance(stmt, MutationStmt):
        return [stmt.target]
    if isinstance(stmt, IncludeStatement):
        included = protocol_lookup.get(stmt.name)
        if included is None or included.name in visited_protocols:
            return []
        nested: list[Expression] = []
        nested_visited = set(visited_protocols)
        nested_visited.add(included.name)
        for nested_stmt in included.statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=nested_visited,
                )
            )
        return nested
    if isinstance(stmt, StepCall):
        if stmt.name == "hold":
            return [_extract_explicit_hold_target(stmt, let_bindings=let_bindings)]
        return _collect_env_target_exprs_from_args(stmt.args)
    if isinstance(stmt, LetStatement):
        return _collect_env_target_exprs_from_expr(stmt.value)
    if isinstance(stmt, AssignStatement):
        return _collect_env_target_exprs_from_expr(stmt.value)
    if isinstance(stmt, ExprStatement):
        return _collect_env_target_exprs_from_expr(stmt.value)
    if isinstance(stmt, WithEnvStmt):
        nested: list[Expression] = []
        for nested_stmt in stmt.statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=visited_protocols,
                )
            )
        return nested
    if isinstance(stmt, WithConstraintStmt):
        nested: list[Expression] = []
        for nested_stmt in stmt.statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=visited_protocols,
                )
            )
        return nested
    if isinstance(stmt, RepeatStatement):
        nested: list[Expression] = []
        for nested_stmt in stmt.statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=visited_protocols,
                )
            )
        return nested
    if isinstance(stmt, IfStatement):
        nested: list[Expression] = []
        for nested_stmt in stmt.then_statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=visited_protocols,
                )
            )
        for nested_stmt in stmt.else_statements:
            nested.extend(
                _collect_env_target_exprs_from_statement(
                    nested_stmt,
                    let_bindings=let_bindings,
                    protocol_lookup=protocol_lookup,
                    visited_protocols=visited_protocols,
                )
            )
        return nested
    return []


def _collect_env_target_exprs_from_expr(expr: Expression) -> list[Expression]:
    if isinstance(expr, CallExpr):
        return _collect_env_target_exprs_from_args(expr.args)
    return []


def _collect_env_target_exprs_from_args(args: list[Arg]) -> list[Expression]:
    return [arg.value for arg in args if arg.name in {"sample", "container"}]


def _expand_mutation_targets(
    target: Expression,
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state: _CompilerState,
) -> tuple[list[IRLet], list[Expression]]:
    return _expand_group_like_target_expr(
        target,
        stmt_id=stmt_id,
        let_bindings=let_bindings,
        state=state,
    )


def _expand_mutation_sources(
    sources: list[Expression],
    *,
    target: Expression,
    flattened_targets: list[Expression],
    let_bindings: dict[str, Expression],
) -> list[list[Expression]]:
    series_sources = [source for source in sources if _is_series_expr(source)]
    if not series_sources:
        return [list(sources) for _ in flattened_targets]

    if not _is_group_like_ast(target, let_bindings):
        raise ValueError("series(...) requires a group-like mutation target")

    cardinality = len(flattened_targets)
    per_target_sources: list[list[Expression]] = [[] for _ in range(cardinality)]
    for source in sources:
        if _is_series_expr(source):
            mapped_pairs = _expand_series_expr(source, cardinality=cardinality)
            for idx, pair in enumerate(mapped_pairs):
                per_target_sources[idx].append(pair)
            continue
        for target_sources in per_target_sources:
            target_sources.append(source)
    return per_target_sources


def _is_series_expr(expr: Expression) -> bool:
    return isinstance(expr, CallExpr) and expr.name == "series"


def _expand_series_expr(expr: Expression, *, cardinality: int) -> list[PairExpr]:
    assert isinstance(expr, CallExpr)
    source_arg = _find_named_arg(expr.args, "source")
    values_arg = _find_named_arg(expr.args, "values")
    if source_arg is None or values_arg is None:
        raise ValueError("series(...) requires 'source' and 'values'")
    if not isinstance(values_arg.value, ListLiteral):
        raise ValueError("series(...) requires a list literal for 'values'")
    values = list(values_arg.value.elements)
    if len(values) != cardinality:
        raise ValueError("series(...) value count must match target group cardinality")
    return [PairExpr(left=source_arg.value, right=value, span=expr.span) for value in values]


def _expand_group_like_target_expr(
    expr: Expression,
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state: _CompilerState,
) -> tuple[list[IRLet], list[Expression]]:
    resolved = _resolve_group_like_bound_expr(expr, let_bindings)
    if isinstance(resolved, GroupExpr):
        prefix: list[IRLet] = []
        members: list[Expression] = []
        for element in resolved.elements:
            if _is_group_like_ast(element, let_bindings):
                raise ValueError("Nested groups are not supported in v0.1 batch authoring")
            nested_prefix, nested_members = _expand_group_like_target_expr(
                element,
                stmt_id=stmt_id,
                let_bindings=let_bindings,
                state=state,
            )
            prefix.extend(nested_prefix)
            members.extend(nested_members)
        return prefix, members
    if isinstance(resolved, PlateSelectorExpr):
        return materialize_plate_selector(
            resolved,
            stmt_id=stmt_id,
            let_bindings=let_bindings,
            state=state,
        )
    return [], [resolved]


def _is_group_like_ast(expr: Expression, let_bindings: dict[str, Expression]) -> bool:
    resolved = _resolve_group_like_bound_expr(expr, let_bindings)
    return isinstance(resolved, (GroupExpr, PlateSelectorExpr))


def _is_env_target_expr(expr: Expression, let_bindings: dict[str, Expression]) -> bool:
    resolved = _resolve_group_like_bound_expr(expr, let_bindings)
    return isinstance(resolved, (Identifier, IndexExpr, MemberExpr, GroupExpr, PlateSelectorExpr))


def _is_explicit_hold_target_expr(expr: Expression, let_bindings: dict[str, Expression]) -> bool:
    resolved = _resolve_hold_target_bound_expr(expr, let_bindings)
    if isinstance(resolved, GroupExpr):
        return all(_is_explicit_hold_target_expr(element, let_bindings) for element in resolved.elements)
    if isinstance(resolved, MemberExpr):
        view = classify_container_target_view(resolved)
        if view is None and not is_container_target_view_namespace_path(resolved):
            return False
        root = view.root if view is not None else resolved
        while isinstance(root, MemberExpr):
            root = root.base
        base = _resolve_group_like_bound_expr(root, let_bindings)
        return isinstance(base, (Identifier, IndexExpr, PlateSelectorExpr))
    return isinstance(resolved, (Identifier, IndexExpr, PlateSelectorExpr))


def _resolve_hold_target_bound_expr(expr: Expression, let_bindings: dict[str, Expression]) -> Expression:
    seen: set[str] = set()
    current = expr
    while (
        isinstance(current, Identifier)
        and current.name in let_bindings
        and current.name not in seen
        and isinstance(let_bindings[current.name], (GroupExpr, PlateSelectorExpr, MemberExpr, IndexExpr))
    ):
        seen.add(current.name)
        current = let_bindings[current.name]
    return current


def _resolve_group_like_bound_expr(expr: Expression, let_bindings: dict[str, Expression]) -> Expression:
    seen: set[str] = set()
    current = expr
    while (
        isinstance(current, Identifier)
        and current.name in let_bindings
        and current.name not in seen
        and isinstance(let_bindings[current.name], (GroupExpr, PlateSelectorExpr))
    ):
        seen.add(current.name)
        current = let_bindings[current.name]
    return current


def materialize_plate_selector(
    selector: PlateSelectorExpr,
    *,
    stmt_id: str,
    let_bindings: dict[str, Expression],
    state: _CompilerState,
) -> tuple[list[IRLet], list[Expression]]:
    plate_name = plate_descriptor_binding(selector.base.name, let_bindings)
    positions = selector_positions([(region.start, region.end) for region in selector.regions])
    prefix: list[IRLet] = []
    members: list[Expression] = []
    for position in positions:
        declarations, identifier = request_plate_well(
            plate_name=plate_name, position=position, stmt_id=stmt_id,
            state=state, span=selector.span,
        )
        prefix.extend(declarations)
        members.append(identifier)
    return prefix, members


def plate_descriptor_binding(name: str, let_bindings: dict[str, Expression]) -> str:
    """Resolve descriptor aliases without evaluating geometry or defaults."""
    seen = set()
    while name not in seen:
        seen.add(name)
        bound = let_bindings.get(name)
        if isinstance(bound, CallExpr) and bound.name == 'plate':
            return name
        if isinstance(bound, Identifier):
            name = bound.name
            continue
        break
    raise ValueError(f"plate selector base '{name}' must resolve to let-bound plate(...)")


def request_plate_well(*, plate_name: str, position: str, stmt_id: str, state: _CompilerState, span):
    """Reserve one symbolic reference; do not allocate a well during compile."""
    key = (plate_name, position)
    existing = state.synthesized_wells.get(key)
    if existing is not None:
        return [], Identifier(name=existing, span=span)
    name = f"__lw_plate_{plate_name}_{position}"
    state.synthesized_wells[key] = name
    return [IRLet(
        id=f"{stmt_id}::well::{position}", name=name,
        value=IRPlateWellRef(plate=IRIdentifier(name=plate_name, span=span), position=position, span=span),
        span=span,
    )], Identifier(name=name, span=span)


def _expr_identity_key(expr: Expression) -> str:
    if isinstance(expr, Identifier):
        return f"id:{expr.name}"
    if isinstance(expr, IndexExpr):
        return f"idx:{_expr_identity_key(expr.base)}:{_expr_identity_key(expr.index)}"
    if isinstance(expr, Quantity):
        return f"q:{expr.value}:{expr.unit}"
    return repr(expr)


def split_env_hold_markers(
    statements: list[Statement],
    *,
    let_bindings: dict[str, Expression],
) -> EnvHoldMarkerSplit:
    hold_targets: list[Expression] = []
    executable_statements: list[Statement] = []
    for stmt in statements:
        if isinstance(stmt, StepCall) and stmt.name == "hold":
            hold_targets.append(_extract_explicit_hold_target(stmt, let_bindings=let_bindings))
            continue
        executable_statements.append(stmt)
    return EnvHoldMarkerSplit(
        hold_targets=hold_targets,
        executable_statements=executable_statements,
        has_invalid_nested_hold=_contains_invalid_hold_statement(executable_statements),
    )


def _contains_invalid_hold_statement(statements: list[Statement]) -> bool:
    for stmt in statements:
        if isinstance(stmt, StepCall) and stmt.name == "hold":
            return True
        if isinstance(stmt, WithEnvStmt):
            continue
        if isinstance(stmt, WithConstraintStmt):
            if _contains_invalid_hold_statement(stmt.statements):
                return True
            continue
        if isinstance(stmt, RepeatStatement):
            if _contains_invalid_hold_statement(stmt.statements):
                return True
            continue
        if isinstance(stmt, IfStatement):
            if _contains_invalid_hold_statement(stmt.then_statements):
                return True
            if _contains_invalid_hold_statement(stmt.else_statements):
                return True
    return False


def _extract_explicit_hold_target(stmt: StepCall, *, let_bindings: dict[str, Expression]) -> Expression:
    if stmt.name != "hold":
        raise ValueError("internal error: explicit hold target requested for non-hold statement")
    if len(stmt.args) != 1 or stmt.args[0].name not in {"target", "sample"}:
        raise ValueError("hold(...) requires exactly one target expression")
    target = stmt.args[0].value
    if not _is_explicit_hold_target_expr(target, let_bindings):
        raise ValueError("hold(...) requires a container/well, container target view, or group-like reference")
    return _resolve_hold_target_bound_expr(target, let_bindings)
