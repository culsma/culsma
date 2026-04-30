from __future__ import annotations

from culsma.parser.ast_nodes import (
    AssignStatement,
    BinaryOp,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStatement,
    Identifier,
    IfStatement,
    LetStatement,
    LibraryImportDecl,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    MutationStmt,
    ProtocolRefStatement,
    Quantity,
    ReturnStatement,
    RepeatStatement,
    SourceIncludeDecl,
    StepCall,
    StringLiteral,
    WithConstraintStmt,
    WithEnvStmt,
)
from culsma.parser.parser import parse


def _single_statement(source: str):
    return parse(f"protocol T {{ {source} }}").protocols[0].statements[0]


def test_top_level_source_string_builds_program_imports_and_protocol():
    program = parse(
        """
        include "common.culs";
        import StdLib;
        protocol T(sample = 1) returns(out) {
            return out = sample;
        }
        """
    )

    assert program.source_includes == [SourceIncludeDecl(path="common.culs", span=program.source_includes[0].span)]
    assert program.library_imports == [LibraryImportDecl(name="StdLib", span=program.library_imports[0].span)]
    protocol = program.protocols[0]
    assert protocol.name == "T"
    assert protocol.params[0].name == "sample"
    assert protocol.returns == ["out"]
    assert isinstance(protocol.statements[0], ReturnStatement)


def test_let_source_string_builds_let_statement_with_call_expression():
    stmt = _single_statement('let x = tube(label = "A");')

    assert isinstance(stmt, LetStatement)
    assert stmt.name == "x"
    assert isinstance(stmt.value, CallExpr)
    assert stmt.value.name == "tube"
    assert stmt.value.args[0].name == "label"
    assert stmt.value.args[0].value == StringLiteral(value="A", span=stmt.value.args[0].value.span)


def test_expression_source_string_builds_binary_expression_tree():
    stmt = _single_statement("let x = (2 + 3) * 4;")

    assert isinstance(stmt, LetStatement)
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "*"
    assert isinstance(stmt.value.left, BinaryOp)
    assert stmt.value.left.op == "+"


def test_assignment_source_strings_build_identifier_and_member_targets():
    program = parse(
        """
        protocol T {
            let read = data();
            total = 5uL;
            read.result.signal = 1;
        }
        """
    )
    identifier_assign = program.protocols[0].statements[1]
    member_assign = program.protocols[0].statements[2]

    assert isinstance(identifier_assign, AssignStatement)
    assert identifier_assign.target == Identifier(name="total", span=identifier_assign.target.span)
    assert isinstance(identifier_assign.value, Quantity)
    assert identifier_assign.value.unit == "uL"
    assert isinstance(member_assign, AssignStatement)
    assert isinstance(member_assign.target, MemberExpr)
    assert member_assign.target.member == "signal"
    assert isinstance(member_assign.target.base, MemberExpr)
    assert member_assign.target.base.member == "result"


def test_return_source_strings_build_positional_and_named_returns():
    program = parse(
        """
        protocol T {
            return result;
        }
        protocol U {
            return out = result;
        }
        """
    )
    positional = program.protocols[0].statements[0]
    named = program.protocols[1].statements[0]

    assert isinstance(positional, ReturnStatement)
    assert isinstance(positional.value, Identifier)
    assert positional.bindings == []
    assert isinstance(named, ReturnStatement)
    assert named.value is None
    assert named.bindings[0].name == "out"
    assert isinstance(named.bindings[0].value, Identifier)


def test_with_env_source_string_builds_env_block_statement():
    stmt = _single_statement("with env(thermal = 37C, duration = 10min) { hold(sample = tube); }")

    assert isinstance(stmt, WithEnvStmt)
    assert [arg.name for arg in stmt.env_args] == ["thermal", "duration"]
    assert isinstance(stmt.env_args[0].value, Quantity)
    assert stmt.env_args[0].value.unit == "C"
    assert isinstance(stmt.statements[0], StepCall)
    assert stmt.statements[0].name == "hold"


def test_with_constraint_source_strings_build_block_and_trailing_forms():
    program = parse(
        """
        protocol T {
            with constraint(gentle, temperature = 4C) { mix(sample = tube); }
            mix(sample = tube) with constraint(preserve_boundary);
        }
        """
    )
    block = program.protocols[0].statements[0]
    trailing = program.protocols[0].statements[1]

    assert isinstance(block, WithConstraintStmt)
    assert block.requirements == ["gentle"]
    assert block.options[0].name == "temperature"
    assert isinstance(block.statements[0], StepCall)
    assert isinstance(trailing, WithConstraintStmt)
    assert trailing.requirements == ["preserve_boundary"]
    assert isinstance(trailing.statements[0], StepCall)


def test_call_statement_source_strings_split_protocol_reference_and_method_statement():
    program = parse(
        """
        protocol T {
            Std.Protocol(sample);
            tube.mix(sample);
        }
        """
    )
    protocol_ref = program.protocols[0].statements[0]
    method_stmt = program.protocols[0].statements[1]

    assert isinstance(protocol_ref, ProtocolRefStatement)
    assert protocol_ref.module == "Std"
    assert protocol_ref.protocol == "Protocol"
    assert protocol_ref.args[0].name == "arg0"
    assert isinstance(method_stmt, ExprStatement)
    assert isinstance(method_stmt.value, MethodCallExpr)
    assert method_stmt.value.method == "mix"


def test_mutation_source_strings_build_pair_and_series_sources():
    stmt = _single_statement("dst << [src:10uL, series(feed, [5uL, 10uL])];")

    assert isinstance(stmt, MutationStmt)
    assert isinstance(stmt.target, Identifier)
    assert len(stmt.sources) == 2
    assert stmt.sources[0].left == Identifier(name="src", span=stmt.sources[0].left.span)
    assert isinstance(stmt.sources[0].right, Quantity)
    assert isinstance(stmt.sources[1], CallExpr)
    assert stmt.sources[1].name == "series"


def test_loop_and_conditional_source_strings_build_block_statements():
    program = parse(
        """
        protocol T {
            repeat 3 { continue; }
            repeat item in items { break; }
            if ready { break; } else { continue; }
        }
        """
    )
    count_repeat = program.protocols[0].statements[0]
    binding_repeat = program.protocols[0].statements[1]
    conditional = program.protocols[0].statements[2]

    assert isinstance(count_repeat, RepeatStatement)
    assert isinstance(count_repeat.times, Quantity)
    assert isinstance(count_repeat.statements[0], ContinueStmt)
    assert isinstance(binding_repeat, RepeatStatement)
    assert binding_repeat.binding == "item"
    assert isinstance(binding_repeat.iterable, Identifier)
    assert isinstance(binding_repeat.statements[0], BreakStmt)
    assert isinstance(conditional, IfStatement)
    assert isinstance(conditional.condition, Identifier)
    assert isinstance(conditional.then_statements[0], BreakStmt)
    assert isinstance(conditional.else_statements[0], ContinueStmt)


def test_markers_source_string_normalizes_to_call_expression_with_list_argument():
    stmt = _single_statement("let m = markers([A, B]);")

    assert isinstance(stmt, LetStatement)
    assert isinstance(stmt.value, CallExpr)
    assert stmt.value.name == "markers"
    assert stmt.value.args[0].name == "items"
    assert isinstance(stmt.value.args[0].value, ListLiteral)
