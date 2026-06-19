from __future__ import annotations

from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.ir_nodes import IRAssign, IRConditional, IRRepeat, IRStatement, IRWithConstraint, IRWithEnv
from culsma.pipeline.scope import ScopeQueryService


def compile_scope_for_source(source: str):
    compile_result = compile_ast(resolve_program(parse(source)).prepared_program)
    return compile_result.ir, ScopeQueryService.from_model(compile_result.analysis.scope)


def walk_statements(statements: list[IRStatement]):
    for stmt in statements:
        yield stmt
        if isinstance(stmt, IRConditional):
            yield from walk_statements(stmt.then_statements)
            yield from walk_statements(stmt.else_statements)
        elif isinstance(stmt, IRRepeat):
            yield from walk_statements(stmt.statements)
        elif isinstance(stmt, (IRWithEnv, IRWithConstraint)):
            yield from walk_statements(stmt.statements)


def test_scope_resolves_outer_local_and_repeat_binding_from_nested_block():
    ir, scope_query = compile_scope_for_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let total = 0;

  repeat cell in events {
    if total == 0 {
      total = total + 1;
    }
  }
}
"""
    )

    statements = list(walk_statements(ir.protocols[0].statements))
    repeat_stmt = next(stmt for stmt in statements if isinstance(stmt, IRRepeat))
    nested_if = next(stmt for stmt in statements if isinstance(stmt, IRConditional))
    total_assign = next(
        stmt
        for stmt in statements
        if isinstance(stmt, IRAssign) and getattr(stmt.target, "name", None) == "total"
    )

    total_resolution = scope_query.resolve_read(total_assign.id, "total")
    cell_resolution = scope_query.resolve_read(total_assign.id, "cell")

    assert scope_query.slot_kind(total_resolution.slot_id or "") == "local"
    assert scope_query.slot_kind(cell_resolution.slot_id or "") == "repeat_binding"
    assert [effect.name for effect in scope_query.assignment_effects(repeat_stmt.id)] == ["total"]
    assert [effect.name for effect in scope_query.assignment_effects(nested_if.id)] == ["total"]


def test_scope_resolves_outer_local_from_with_env_block():
    ir, scope_query = compile_scope_for_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  let total = 0;

  with env(thermal = 37C, duration = 10min) {
    hold(sample = tube1);
    total = total + 1;
  }
}
"""
    )

    statements = list(walk_statements(ir.protocols[0].statements))
    with_env = next(stmt for stmt in statements if isinstance(stmt, IRWithEnv))
    total_assign = next(
        stmt
        for stmt in statements
        if isinstance(stmt, IRAssign) and getattr(stmt.target, "name", None) == "total"
    )

    total_resolution = scope_query.resolve_read(total_assign.id, "total")

    assert scope_query.slot_kind(total_resolution.slot_id or "") == "local"
    assert [effect.name for effect in scope_query.assignment_effects(with_env.id)] == ["total"]
