"""
Tests for the Culsma parser.

Covers:
1. Parsing fixture files without errors
2. AST structure assertions (protocol names, statement counts, parameter values)
3. Quantity unit splitting (200uL -> value=200, unit="uL")
4. Variable references preserved as Identifier nodes
5. Invalid input raises errors
"""

from pathlib import Path

import pytest
from lark.exceptions import UnexpectedInput, VisitError

from culsma.common.source import Span
from culsma.parser.parser import parse, parse_file, parse_files
from culsma.parser.ast_nodes import (
    AssignStatement,
    Arg,
    BinaryOp,
    BooleanLiteral,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStatement,
    GroupExpr,
    IncludeStatement,
    Identifier,
    IndexExpr,
    IfStatement,
    LibraryImportDecl,
    LetStatement,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    MutationStmt,
    ParamDecl,
    PairExpr,
    PlateSelectorExpr,
    ProtocolRefStatement,
    Program,
    ProtocolDecl,
    Quantity,
    ReturnBinding,
    ReturnStatement,
    RepeatStatement,
    SourceIncludeDecl,
    StepCall,
    StringLiteral,
    UnaryOp,
    WithConstraintStmt,
    WithEnvStmt,
)

FIXTURES = Path(__file__).parent / "fixtures_parser"
CURRENT_CORE_FIXTURE = FIXTURES / "current_frontend_core.culs"
CURRENT_READOUT_FIXTURE = FIXTURES / "current_frontend_readout.culs"


# ============================================================
# 1. Fixture files parse without errors
# ============================================================

class TestFixtureParsing:

    def test_current_frontend_core_parses(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        assert isinstance(ast, Program)
        assert len(ast.protocols) == 1

    def test_current_frontend_readout_parses(self):
        ast = parse_file(CURRENT_READOUT_FIXTURE)
        assert isinstance(ast, Program)
        assert len(ast.protocols) == 1

    def test_parse_files_merges_programs(self):
        ast = parse_files([CURRENT_CORE_FIXTURE, CURRENT_READOUT_FIXTURE])
        assert isinstance(ast, Program)
        assert len(ast.protocols) == 2


# ============================================================
# 2. AST structure assertions
# ============================================================

class TestASTStructure:

    def test_current_core_protocol_name(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        assert proto.name == "CurrentFrontendCore"

    def test_current_core_top_level_statement_shape(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        assert len(proto.statements) == 10
        assert isinstance(proto.statements[5], WithEnvStmt)
        assert isinstance(proto.statements[6], LetStatement)
        assert isinstance(proto.statements[7], LetStatement)
        assert isinstance(proto.statements[8], LetStatement)
        assert isinstance(proto.statements[9], MutationStmt)

    def test_assignment_statement_parses(self):
        ast = parse("protocol T { let total = 0uL; total = total + 50uL; }")
        proto = ast.protocols[0]
        assert isinstance(proto.statements[0], LetStatement)
        assert isinstance(proto.statements[1], AssignStatement)
        assign = proto.statements[1]
        assert isinstance(assign.target, Identifier)
        assert assign.target.name == "total"
        assert isinstance(assign.value, BinaryOp)
        assert assign.value.op == "+"

    def test_member_assignment_statement_parses(self):
        ast = parse('protocol T { let read = data_ref(kind = sequence_read); read.result.sequence = []; }')
        assign = ast.protocols[0].statements[1]
        assert isinstance(assign, AssignStatement)
        assert isinstance(assign.target, MemberExpr)
        assert assign.target.member == "sequence"
        assert isinstance(assign.target.base, MemberExpr)
        assert assign.target.base.member == "result"
        assert isinstance(assign.target.base.base, Identifier)
        assert assign.target.base.base.name == "read"
        assert isinstance(assign.value, ListLiteral)

    def test_current_core_let_statements(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        lets = [s for s in proto.statements if isinstance(s, LetStatement)]
        assert [stmt.name for stmt in lets] == [
            "sample_tube",
            "feed_stock",
            "gradient_tube",
            "stop_now",
            "skip_now",
            "sep_group",
            "frac_group",
            "img_obs",
        ]

    def test_current_core_with_env_body_shape(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        with_env = proto.statements[5]
        assert isinstance(with_env, WithEnvStmt)
        assert [arg.name for arg in with_env.env_args] == ["thermal", "duration"]
        loop = with_env.statements[0]
        assert isinstance(loop, RepeatStatement)
        assert len(loop.statements) == 3
        assert isinstance(loop.statements[0], IfStatement)
        assert isinstance(loop.statements[1], IfStatement)
        assert isinstance(loop.statements[2], MutationStmt)

    def test_current_core_program_call_lets(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        sep_let = proto.statements[6]
        frac_let = proto.statements[7]
        img_let = proto.statements[8]
        assert isinstance(sep_let, LetStatement)
        assert isinstance(sep_let.value, CallExpr)
        assert sep_let.value.name == "sep"
        assert isinstance(frac_let.value, CallExpr)
        assert frac_let.value.name == "frac"
        assert isinstance(img_let.value, CallExpr)
        assert img_let.value.name == "img"

    def test_group_constructor_and_plate_selector_parse(self):
        ast = parse(
            'protocol T { let plate96 = plate(label = "P", format = "96well", carrier_id = "P1"); '
            'let g = group([tube1, tube2]); let block = plate96[A1:B2, D1]; }'
        )
        proto = ast.protocols[0]
        group_let = proto.statements[1]
        selector_let = proto.statements[2]
        assert isinstance(group_let, LetStatement)
        assert isinstance(group_let.value, GroupExpr)
        assert len(group_let.value.elements) == 2
        assert isinstance(selector_let.value, PlateSelectorExpr)
        assert selector_let.value.base.name == "plate96"
        assert [(region.start, region.end) for region in selector_let.value.regions] == [
            ("A1", "B2"),
            ("D1", None),
        ]

    def test_with_env_accepts_group_target_binding(self):
        ast = parse(
            'protocol T { let g = group([tube1, tube2]); with env(thermal = 37C, duration = 10min) { hold(sample = g); } }'
        )
        with_env = ast.protocols[0].statements[1]
        assert isinstance(with_env, WithEnvStmt)
        hold_stmt = with_env.statements[0]
        assert isinstance(hold_stmt, StepCall)
        assert hold_stmt.args[0].name == "sample"
        assert isinstance(hold_stmt.args[0].value, Identifier)
        assert hold_stmt.args[0].value.name == "g"

    def test_mutation_accepts_plate_selector_target(self):
        ast = parse(
            'protocol T { let plate96 = plate(label = "P", format = "96well", carrier_id = "P1"); '
            'plate96[A1:A2] << [feed:10uL]; }'
        )
        mutation = ast.protocols[0].statements[1]
        assert isinstance(mutation, MutationStmt)
        assert isinstance(mutation.target, PlateSelectorExpr)

    def test_mutation_accepts_series_ordered_mapping_source(self):
        ast = parse(
            'protocol T { let plate96 = plate(label = "P", format = "96well", carrier_id = "P1"); '
            'plate96[A1:A3] << [series(feed, [5uL, 10uL, 20uL])]; }'
        )
        mutation = ast.protocols[0].statements[1]
        assert isinstance(mutation, MutationStmt)
        assert len(mutation.sources) == 1
        assert isinstance(mutation.sources[0], CallExpr)
        assert mutation.sources[0].name == "series"

    def test_mutation_stmt_without_exec_options_is_current_surface(self):
        ast = parse('protocol T { dst << [src:10uL]; }')
        mutation = ast.protocols[0].statements[0]
        assert isinstance(mutation, MutationStmt)
        assert not hasattr(mutation, "exec_options")

    def test_with_constraint_block_parses(self):
        ast = parse(
            'protocol T { with constraint(gentle, preserve_boundary) { dst << [src:10uL]; } }'
        )
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithConstraintStmt)
        assert stmt.requirements == ["gentle", "preserve_boundary"]
        assert stmt.options == []
        assert len(stmt.statements) == 1
        assert isinstance(stmt.statements[0], MutationStmt)

    def test_trailing_with_constraint_sugar_parses(self):
        ast = parse(
            'protocol T { dst << [src:10uL] with constraint(gentle, preserve_boundary); }'
        )
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithConstraintStmt)
        assert stmt.requirements == ["gentle", "preserve_boundary"]
        assert len(stmt.statements) == 1
        assert isinstance(stmt.statements[0], MutationStmt)

    def test_call_expr_accepts_plate_selector_argument(self):
        ast = parse(
            'protocol T { let plate96 = plate(label = "P", format = "96well", carrier_id = "P1"); '
            'let obs = img(sample = plate96[A1:B2], quantity = fluorescence); }'
        )
        readout = ast.protocols[0].statements[1]
        assert isinstance(readout, LetStatement)
        assert isinstance(readout.value, CallExpr)
        sample_arg = next(arg for arg in readout.value.args if arg.name == "sample")
        assert isinstance(sample_arg.value, PlateSelectorExpr)

    def test_member_access_parses_as_chained_member_expr(self):
        ast = parse(
            'protocol T { let x = obs.result.signal; }'
        )
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, MemberExpr)
        assert let_stmt.value.member == "signal"
        assert isinstance(let_stmt.value.base, MemberExpr)
        assert let_stmt.value.base.member == "result"

    def test_method_call_expression_parses(self):
        ast = parse('protocol T { let ok = detector_surface.detects(ion); }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, MethodCallExpr)
        assert let_stmt.value.method == "detects"
        assert isinstance(let_stmt.value.base, Identifier)
        assert let_stmt.value.base.name == "detector_surface"
        assert len(let_stmt.value.args) == 1
        assert isinstance(let_stmt.value.args[0], Identifier)
        assert let_stmt.value.args[0].name == "ion"

    def test_method_call_statement_parses(self):
        ast = parse('protocol T { seq_data.items.append(read); }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, ExprStatement)
        assert isinstance(stmt.value, MethodCallExpr)
        assert stmt.value.method == "append"
        assert isinstance(stmt.value.base, MemberExpr)
        assert stmt.value.base.member == "items"
        assert isinstance(stmt.value.base.base, Identifier)
        assert stmt.value.base.base.name == "seq_data"

    def test_markers_list_sugar_lowers_to_markers_call(self):
        ast = parse('protocol T { let panel = markers(["CD3", "CD19"]); }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, CallExpr)
        assert let_stmt.value.name == "markers"
        assert len(let_stmt.value.args) == 1
        arg = let_stmt.value.args[0]
        assert arg.name == "items"
        assert isinstance(arg.value, ListLiteral)
        assert [item.value for item in arg.value.elements] == ["CD3", "CD19"]

    def test_markers_bare_identifier_list_does_not_parse_as_plate_selector(self):
        ast = parse('protocol T { let panel = markers([CD3, CD19]); }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, CallExpr)
        assert let_stmt.value.name == "markers"
        arg = let_stmt.value.args[0]
        assert isinstance(arg.value, ListLiteral)
        assert all(isinstance(item, Identifier) for item in arg.value.elements)
        assert [item.name for item in arg.value.elements] == ["CD3", "CD19"]

    def test_well_like_bare_identifier_list_remains_plain_list(self):
        ast = parse('protocol T { let xs = [CD3, CD19]; }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, ListLiteral)
        assert all(isinstance(item, Identifier) for item in let_stmt.value.elements)
        assert [item.name for item in let_stmt.value.elements] == ["CD3", "CD19"]

    def test_stream_surface_call_parses_with_required_and_optional_args(self):
        ast = parse('protocol T { let events = stream(sample = tube_a, unit = single_cell, panel = panel); }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, CallExpr)
        assert let_stmt.value.name == "stream"
        assert [arg.name for arg in let_stmt.value.args] == ["sample", "unit", "panel"]
        assert isinstance(let_stmt.value.args[0].value, Identifier)
        assert let_stmt.value.args[0].value.name == "tube_a"
        assert isinstance(let_stmt.value.args[1].value, Identifier)
        assert let_stmt.value.args[1].value.name == "single_cell"
        assert isinstance(let_stmt.value.args[2].value, Identifier)
        assert let_stmt.value.args[2].value.name == "panel"

    def test_data_schema_surface_call_parses_label_and_fields(self):
        ast = parse('protocol T { let schema = data_schema(label = "SeqSignal", fields = [signal, intensity]); }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        assert isinstance(let_stmt.value, CallExpr)
        assert let_stmt.value.name == "data_schema"
        assert [arg.name for arg in let_stmt.value.args] == ["label", "fields"]
        assert isinstance(let_stmt.value.args[0].value, StringLiteral)
        assert let_stmt.value.args[0].value.value == "SeqSignal"
        assert isinstance(let_stmt.value.args[1].value, ListLiteral)
        assert all(isinstance(item, Identifier) for item in let_stmt.value.args[1].value.elements)
        assert [item.name for item in let_stmt.value.args[1].value.elements] == ["signal", "intensity"]


# ============================================================
# 3. Quantity unit splitting
# ============================================================

class TestQuantityParsing:

    def test_quantity_with_unit(self):
        ast = parse('protocol T { let x = 200uL; }')
        let_stmt = ast.protocols[0].statements[0]
        assert isinstance(let_stmt, LetStatement)
        q = let_stmt.value
        assert isinstance(q, Quantity)
        assert q.value == 200.0
        assert q.unit == "uL"

    def test_quantity_without_unit(self):
        ast = parse('protocol T { let x = 35; }')
        q = ast.protocols[0].statements[0].value
        assert isinstance(q, Quantity)
        assert q.value == 35.0
        assert q.unit is None

    def test_quantity_decimal(self):
        ast = parse('protocol T { let x = 12.5mL; }')
        q = ast.protocols[0].statements[0].value
        assert isinstance(q, Quantity)
        assert q.value == 12.5
        assert q.unit == "mL"

    def test_quantity_rpm(self):
        ast = parse('protocol T { let x = 12000rpm; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 12000.0
        assert q.unit == "rpm"

    def test_quantity_celsius(self):
        ast = parse('protocol T { let x = 37C; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 37.0
        assert q.unit == "C"

    def test_quantity_nanometer(self):
        ast = parse('protocol T { let x = 260nm; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 260.0
        assert q.unit == "nm"

    def test_quantity_minutes(self):
        ast = parse('protocol T { let x = 10min; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 10.0
        assert q.unit == "min"

    def test_quantity_seconds_short(self):
        ast = parse('protocol T { let x = 30s; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 30.0
        assert q.unit == "s"

    def test_quantity_seconds_long(self):
        ast = parse('protocol T { let x = 30sec; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 30.0
        assert q.unit == "sec"

    def test_quantity_days(self):
        ast = parse('protocol T { let x = 3day; }')
        statements = ast.protocols[0].statements
        assert statements[0].value.value == 3.0
        assert statements[0].value.unit == "day"

    def test_quantity_year_is_not_active_duration_unit(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { with env(thermal = -80C, duration = 2year) { hold(sample = tube); } }')

    def test_quantity_concentration(self):
        ast = parse('protocol T { let x = 50nM; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 50.0
        assert q.unit == "nM"

    def test_quantity_compound_unit(self):
        ast = parse('protocol T { let x = 100ng_per_uL; }')
        q = ast.protocols[0].statements[0].value
        assert q.value == 100.0
        assert q.unit == "ng_per_uL"


# ============================================================
# 4. Variable references as Identifier nodes
# ============================================================

class TestIdentifierReferences:

    def test_variable_reference_in_with_env_conditions(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        with_env = proto.statements[5]
        loop = with_env.statements[0]
        first_if = loop.statements[0]
        second_if = loop.statements[1]
        assert isinstance(first_if.condition, Identifier)
        assert first_if.condition.name == "stop_now"
        assert isinstance(second_if.condition, Identifier)
        assert second_if.condition.name == "skip_now"


# ============================================================
# 5. Expression features
# ============================================================

class TestExpressions:

    def test_list_literal(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        sample_let = proto.statements[0]
        tube_call = sample_let.value
        load_arg = tube_call.args[2]
        lst = load_arg.value
        assert isinstance(lst, ListLiteral)
        assert len(lst.elements) == 1
        assert isinstance(lst.elements[0], PairExpr)
        assert isinstance(lst.elements[0].left, CallExpr)
        assert lst.elements[0].left.name == "content"

    def test_empty_list(self):
        ast = parse('protocol T { Step(items = []); }')
        step = ast.protocols[0].statements[0]
        assert isinstance(step.args[0].value, ListLiteral)
        assert step.args[0].value.elements == []

    def test_boolean_true(self):
        ast = parse('protocol T { Step(flag = true); }')
        val = ast.protocols[0].statements[0].args[0].value
        assert isinstance(val, BooleanLiteral)
        assert val.value is True

    def test_boolean_false(self):
        ast = parse('protocol T { Step(flag = false); }')
        val = ast.protocols[0].statements[0].args[0].value
        assert isinstance(val, BooleanLiteral)
        assert val.value is False

    def test_arithmetic_add(self):
        ast = parse('protocol T { let x = 200uL + 5uL; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == "+"
        assert isinstance(val.left, Quantity)
        assert isinstance(val.right, Quantity)

    def test_arithmetic_precedence(self):
        # 2 + 3 * 4 should parse as 2 + (3 * 4)
        ast = parse('protocol T { let x = 2 + 3 * 4; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == "+"
        assert isinstance(val.left, Quantity)
        assert val.left.value == 2.0
        assert isinstance(val.right, BinaryOp)
        assert val.right.op == "*"

    def test_comparison(self):
        ast = parse('protocol T { let x = 10 > 5; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == ">"

    def test_unary_negation(self):
        ast = parse('protocol T { let x = -5; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, UnaryOp)
        assert val.op == "-"
        assert isinstance(val.operand, Quantity)
        assert val.operand.value == 5.0

    def test_parenthesized_expression(self):
        # (2 + 3) * 4 should parse as (2 + 3) * 4
        ast = parse('protocol T { let x = (2 + 3) * 4; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == "*"
        assert isinstance(val.left, BinaryOp)
        assert val.left.op == "+"

    def test_logical_and(self):
        ast = parse('protocol T { let x = true and false; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == "and"

    def test_logical_or(self):
        ast = parse('protocol T { let x = true or false; }')
        val = ast.protocols[0].statements[0].value
        assert isinstance(val, BinaryOp)
        assert val.op == "or"


# ============================================================
# 6. Comments
# ============================================================

class TestComments:

    def test_line_comment(self):
        src = """
        protocol T {
            // This is a comment
            let x = 5;
        }
        """
        ast = parse(src)
        assert len(ast.protocols[0].statements) == 1

    def test_block_comment(self):
        src = """
        protocol T {
            /* This is a
               block comment */
            let x = 5;
        }
        """
        ast = parse(src)
        assert len(ast.protocols[0].statements) == 1


# ============================================================
# 7. include statement
# ============================================================

class TestIncludeStatement:

    def test_include_statement(self):
        ast = parse('protocol T { include SomeProtocol; }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, IncludeStatement)
        assert stmt.name == "SomeProtocol"

    def test_protocol_ref_statement_python_style(self):
        ast = parse("protocol T { module_core.LysisAndExtraction(); }")
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, ProtocolRefStatement)
        assert stmt.module == "module_core"
        assert stmt.protocol == "LysisAndExtraction"
        assert stmt.args == []

    def test_protocol_ref_statement_python_style_with_named_args(self):
        ast = parse("protocol T { module_core.LysisAndExtraction(buffer = 200uL, temp = 37C); }")
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, ProtocolRefStatement)
        assert stmt.module == "module_core"
        assert stmt.protocol == "LysisAndExtraction"
        assert [a.name for a in stmt.args] == ["buffer", "temp"]


class TestProtocolParams:

    def test_protocol_decl_with_params(self):
        ast = parse("protocol T(a, b = 2, c = 3uL) {}")
        proto = ast.protocols[0]
        assert isinstance(proto, ProtocolDecl)
        assert [p.name for p in proto.params] == ["a", "b", "c"]
        assert isinstance(proto.params[0], ParamDecl)
        assert proto.params[0].default is None
        assert isinstance(proto.params[1].default, Quantity)
        assert proto.params[1].default.value == 2.0
        assert proto.params[1].default.unit is None
        assert isinstance(proto.params[2].default, Quantity)
        assert proto.params[2].default.unit == "uL"

    def test_protocol_decl_without_param_list_remains_valid(self):
        ast = parse("protocol T { Step(); }")
        assert ast.protocols[0].params == []

    def test_protocol_decl_with_returns_contract(self):
        ast = parse("protocol T(sample) returns (prepared_out, seq_out) { return prepared_out = sample, seq_out = sample; }")
        proto = ast.protocols[0]
        assert proto.returns == ["prepared_out", "seq_out"]

    def test_protocol_tail_return_statement(self):
        ast = parse("protocol T(sample) { return sample; }")
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, ReturnStatement)
        assert stmt.bindings == []
        assert isinstance(stmt.value, Identifier)
        assert stmt.value.name == "sample"

    def test_named_return_statement_parses(self):
        ast = parse("protocol T(sample) returns (prepared_out, seq_out) { return prepared_out = sample, seq_out = sample; }")
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, ReturnStatement)
        assert stmt.value is None
        assert len(stmt.bindings) == 2
        assert all(isinstance(binding, ReturnBinding) for binding in stmt.bindings)
        assert [binding.name for binding in stmt.bindings] == ["prepared_out", "seq_out"]


# ============================================================
# 8. source-level include declaration
# ============================================================

class TestSourceIncludeDecl:

    def test_source_include_decl(self):
        ast = parse('include "common/base.culs"; protocol T {}')
        assert len(ast.source_includes) == 1
        source_inc = ast.source_includes[0]
        assert isinstance(source_inc, SourceIncludeDecl)
        assert source_inc.path == "common/base.culs"
        assert len(ast.protocols) == 1
        assert ast.protocols[0].name == "T"

    def test_source_include_must_be_string_path(self):
        with pytest.raises(UnexpectedInput):
            parse("include SomeProtocol; protocol T {}")

    def test_source_include_must_be_before_protocol_decls(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T {} include "shared.culs";')


class TestLibraryImportDecl:

    def test_library_import_decl(self):
        ast = parse("import Bio; protocol T {}")
        assert len(ast.library_imports) == 1
        import_decl = ast.library_imports[0]
        assert isinstance(import_decl, LibraryImportDecl)
        assert import_decl.name == "Bio"
        assert len(ast.protocols) == 1
        assert ast.protocols[0].name == "T"

    def test_library_import_must_be_identifier(self):
        with pytest.raises(UnexpectedInput):
            parse('import "Bio"; protocol T {}')

    def test_library_import_must_be_before_protocol_decls(self):
        with pytest.raises(UnexpectedInput):
            parse("protocol T {} import Bio;")


# ============================================================
# 9. parse_files workspace include loading
# ============================================================

class TestParseFilesWorkspaceInclude:

    def test_parse_files_loads_recursive_source_include_graph(self, tmp_path: Path):
        shared = tmp_path / "shared.culs"
        shared.write_text("protocol Shared { let x = 1; }", encoding="utf-8")

        middle = tmp_path / "middle.culs"
        middle.write_text(
            '\n'.join(
                [
                    'include "shared.culs";',
                    "protocol Middle {",
                    "  include Shared;",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        root = tmp_path / "root.culs"
        root.write_text(
            '\n'.join(
                [
                    'include "middle.culs";',
                    "protocol Root {",
                    "  include Middle;",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        ast = parse_files([root])
        assert [p.name for p in ast.protocols] == ["Shared", "Middle", "Root"]
        assert [p.module for p in ast.protocols] == ["shared", "middle", "root"]

    def test_parse_files_deduplicates_repeated_source_include(self, tmp_path: Path):
        shared = tmp_path / "shared.culs"
        shared.write_text("protocol Shared {}", encoding="utf-8")

        a = tmp_path / "a.culs"
        a.write_text('include "shared.culs";\nprotocol A {}', encoding="utf-8")

        b = tmp_path / "b.culs"
        b.write_text('include "shared.culs";\nprotocol B {}', encoding="utf-8")

        root = tmp_path / "root.culs"
        root.write_text('include "a.culs";\ninclude "b.culs";\nprotocol Root {}', encoding="utf-8")

        ast = parse_files([root])
        assert [p.name for p in ast.protocols] == ["Shared", "A", "B", "Root"]

    def test_parse_files_rejects_include_cycle(self, tmp_path: Path):
        a = tmp_path / "a.culs"
        b = tmp_path / "b.culs"
        a.write_text('include "b.culs";\nprotocol A {}', encoding="utf-8")
        b.write_text('include "a.culs";\nprotocol B {}', encoding="utf-8")

        with pytest.raises(ValueError, match="Include cycle detected"):
            parse_files([a])

    def test_parse_files_rejects_missing_include_target(self, tmp_path: Path):
        root = tmp_path / "root.culs"
        root.write_text('include "missing.culs";\nprotocol Root {}', encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="Included source file not found"):
            parse_files([root])

    def test_parse_files_rejects_duplicate_protocol_names(self, tmp_path: Path):
        a = tmp_path / "a.culs"
        b = tmp_path / "b.culs"
        a.write_text("protocol SharedName {}", encoding="utf-8")
        b.write_text("protocol SharedName {}", encoding="utf-8")

        with pytest.raises(ValueError, match="Duplicate protocol name 'SharedName'"):
            parse_files([a, b])
        with pytest.raises(ValueError, match="LOAD_DUPLICATE_PROTOCOL_NAME"):
            parse_files([a, b])

    def test_parse_files_rejects_duplicate_module_names(self, tmp_path: Path):
        mod_a = tmp_path / "x" / "common.culs"
        mod_b = tmp_path / "y" / "common.culs"
        mod_a.parent.mkdir(parents=True, exist_ok=True)
        mod_b.parent.mkdir(parents=True, exist_ok=True)
        mod_a.write_text("protocol A {}", encoding="utf-8")
        mod_b.write_text("protocol B {}", encoding="utf-8")

        with pytest.raises(ValueError, match="Duplicate module name 'common'"):
            parse_files([mod_a, mod_b])

    def test_parse_files_rejects_missing_entry_protocol(self, tmp_path: Path):
        root = tmp_path / "root.culs"
        root.write_text("protocol Root {}", encoding="utf-8")

        with pytest.raises(ValueError, match="LOAD_ENTRY_PROTOCOL_NOT_FOUND"):
            parse_files([root], entry_protocol="MissingEntry")


# ============================================================
# 10. repeat statement
# ============================================================

class TestRepeatStatement:

    def test_repeat_parses_with_block(self):
        ast = parse('protocol T { repeat 3 { Step(v = 1); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, RepeatStatement)
        assert stmt.binding is None
        assert stmt.iterable is None
        assert isinstance(stmt.times, Quantity)
        assert stmt.times.value == 3.0
        assert stmt.times.unit is None
        assert len(stmt.statements) == 1
        assert isinstance(stmt.statements[0], StepCall)

    def test_repeat_allows_nested_repeat(self):
        ast = parse('protocol T { repeat 2 { repeat 3 { Step(v = 1); } } }')
        outer = ast.protocols[0].statements[0]
        assert isinstance(outer, RepeatStatement)
        assert len(outer.statements) == 1
        inner = outer.statements[0]
        assert isinstance(inner, RepeatStatement)
        assert isinstance(inner.times, Quantity)
        assert inner.times.value == 3.0

    def test_repeat_schedule_binding_parses(self):
        ast = parse('protocol T { repeat t in schedule(start = 30min, step = 30min) { Step(v = t); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, RepeatStatement)
        assert stmt.times is None
        assert stmt.binding == "t"
        assert isinstance(stmt.iterable, CallExpr)
        assert stmt.iterable.name == "schedule"
        assert [arg.name for arg in stmt.iterable.args] == ["start", "step"]


# ============================================================
# 11. if statement
# ============================================================

class TestIfStatement:

    def test_if_parses_without_else(self):
        ast = parse('protocol T { if true { Step(v = 1); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, IfStatement)
        assert isinstance(stmt.condition, BooleanLiteral)
        assert stmt.condition.value is True
        assert len(stmt.then_statements) == 1
        assert stmt.else_statements == []

    def test_if_parses_with_else(self):
        ast = parse('protocol T { if true { Step(v = 1); } else { Step(v = 2); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, IfStatement)
        assert len(stmt.then_statements) == 1
        assert len(stmt.else_statements) == 1
        assert isinstance(stmt.then_statements[0], StepCall)
        assert isinstance(stmt.else_statements[0], StepCall)


# ============================================================
# 12. New parser surface: with env / mutation / call expr / index expr
# ============================================================

class TestWithEnvStatement:

    def test_with_env_scalar_parses(self):
        ast = parse('protocol T { with env(thermal = 37C, duration = 30min) { StepA(); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithEnvStmt)
        assert [arg.name for arg in stmt.env_args] == ["thermal", "duration"]
        assert isinstance(stmt.env_args[0].value, Quantity)
        assert len(stmt.statements) == 1
        assert isinstance(stmt.statements[0], StepCall)

    def test_with_env_program_call_and_explicit_hold(self):
        ast = parse(
            'protocol T { with env(thermal = thermal_program(from = 60C, to = 95C, duration = 350s)) { hold(sample = pcr_well); } }'
        )
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithEnvStmt)
        assert len(stmt.env_args) == 1
        thermal_arg = stmt.env_args[0]
        assert thermal_arg.name == "thermal"
        assert isinstance(thermal_arg.value, CallExpr)
        assert thermal_arg.value.name == "thermal_program"
        assert [arg.name for arg in thermal_arg.value.args] == ["from", "to", "duration"]
        assert len(stmt.statements) == 1
        assert isinstance(stmt.statements[0], StepCall)
        assert stmt.statements[0].args[0].name == "sample"

    def test_with_env_positional_hold_target_parses(self):
        ast = parse(
            'protocol T { with env(thermal = thermal_program(from = 60C, duration = 30s)) { hold(pcr_well); } }'
        )
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithEnvStmt)
        assert isinstance(stmt.statements[0], StepCall)
        assert stmt.statements[0].name == "hold"
        assert stmt.statements[0].args[0].name == "target"
        assert isinstance(stmt.statements[0].args[0].value, Identifier)
        assert stmt.statements[0].args[0].value.name == "pcr_well"

    def test_with_env_hold_structure_target_parses_as_member(self):
        ast = parse('protocol T { with env(thermal = 105C, duration = 5min) { hold(pcr_tube.structure.top); } }')
        stmt = ast.protocols[0].statements[0]
        target = stmt.statements[0].args[0].value
        assert target.__class__.__name__ == "MemberExpr"
        assert target.member == "top"
        assert isinstance(target.base, MemberExpr)
        assert target.base.member == "structure"
        assert isinstance(target.base.base, Identifier)
        assert target.base.base.name == "pcr_tube"

    def test_with_env_supports_multiple_targets_and_index_target(self):
        ast = parse('protocol T { with env(thermal = 4C, duration = 2min) { hold(sample = group([tube_a, frac_group[3]])); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithEnvStmt)
        hold_target = stmt.statements[0].args[0].value
        assert isinstance(hold_target, GroupExpr)
        assert len(hold_target.elements) == 2
        assert isinstance(hold_target.elements[0], Identifier)
        assert isinstance(hold_target.elements[1], IndexExpr)
        assert isinstance(hold_target.elements[1].base, Identifier)
        assert hold_target.elements[1].base.name == "frac_group"


class TestMutationStatement:

    def test_mutation_stmt_quantified_sources(self):
        ast = parse('protocol T { dst << [src:20uL]; }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, MutationStmt)
        assert isinstance(stmt.target, Identifier)
        assert stmt.target.name == "dst"
        assert len(stmt.sources) == 1
        source = stmt.sources[0]
        assert isinstance(source, PairExpr)
        assert isinstance(source.left, Identifier)
        assert source.left.name == "src"
        assert isinstance(source.right, Quantity)
        assert source.right.unit == "uL"
        assert not hasattr(stmt, "exec_options")

    def test_mutation_stmt_full_sources_and_index_target(self):
        ast = parse('protocol T { sep_group[0] << [a, b]; }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, MutationStmt)
        assert isinstance(stmt.target, IndexExpr)
        assert len(stmt.sources) == 2
        assert all(isinstance(item, Identifier) for item in stmt.sources)
        assert not hasattr(stmt, "exec_options")


class TestBreakContinueStatements:

    def test_break_statement_parses(self):
        ast = parse('protocol T { repeat 3 { break; } }')
        repeat_stmt = ast.protocols[0].statements[0]
        assert isinstance(repeat_stmt, RepeatStatement)
        assert isinstance(repeat_stmt.statements[0], BreakStmt)

    def test_continue_statement_parses(self):
        ast = parse('protocol T { repeat 3 { continue; } }')
        repeat_stmt = ast.protocols[0].statements[0]
        assert isinstance(repeat_stmt, RepeatStatement)
        assert isinstance(repeat_stmt.statements[0], ContinueStmt)


class TestCallAndIndexExpressions:

    def test_let_rhs_accepts_call_expr(self):
        ast = parse('protocol T { let sep_group = sep(sample = lysate, program = sep_program(mode = "centrifuge")); }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, LetStatement)
        assert isinstance(stmt.value, CallExpr)
        assert stmt.value.name == "sep"
        assert [arg.name for arg in stmt.value.args] == ["sample", "program"]
        assert isinstance(stmt.value.args[1].value, CallExpr)
        assert stmt.value.args[1].value.name == "sep_program"

    def test_index_expr_parses_in_arg_value(self):
        ast = parse('protocol T { img(sample = frac_group[3], quantity = fluorescence); }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, StepCall)
        sample_arg = stmt.args[0]
        assert sample_arg.name == "sample"
        assert isinstance(sample_arg.value, IndexExpr)
        assert isinstance(sample_arg.value.base, Identifier)
        assert sample_arg.value.base.name == "frac_group"
        assert isinstance(sample_arg.value.index, Quantity)
        assert sample_arg.value.index.value == 3.0

    def test_constructor_load_accepts_pair_expr(self):
        ast = parse('protocol T { let dna = tube(label = "DNA", capacity = 500uL, load = [content(code = "S1", type = "sample_dna"):100uL]); }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, LetStatement)
        assert isinstance(stmt.value, CallExpr)
        load_arg = stmt.value.args[2]
        assert load_arg.name == "load"
        assert isinstance(load_arg.value, ListLiteral)
        pair_item = load_arg.value.elements[0]
        assert isinstance(pair_item, PairExpr)
        assert isinstance(pair_item.left, CallExpr)
        assert pair_item.left.name == "content"
        assert isinstance(pair_item.right, Quantity)
        assert pair_item.right.value == 100.0

    def test_quantity_units_cover_percent_volt_millivolt_and_ms(self):
        ast = parse('protocol T { let a = 5%; let b = 100V; let c = 200ms; let d = 50mV; }')
        a_stmt, b_stmt, c_stmt, d_stmt = ast.protocols[0].statements
        assert isinstance(a_stmt.value, Quantity)
        assert a_stmt.value.unit == "%"
        assert b_stmt.value.unit == "V"
        assert c_stmt.value.unit == "ms"
        assert d_stmt.value.unit == "mV"


# ============================================================
# 13. Edge cases
# ============================================================

class TestEdgeCases:

    def test_empty_protocol(self):
        ast = parse('protocol Empty {}')
        assert len(ast.protocols) == 1
        assert ast.protocols[0].statements == []

    def test_empty_program(self):
        ast = parse('')
        assert ast.protocols == []
        assert ast.source_includes == []

    def test_step_call_no_args(self):
        ast = parse('protocol T { Noop(); }')
        step = ast.protocols[0].statements[0]
        assert isinstance(step, StepCall)
        assert step.name == "Noop"
        assert step.args == []

    def test_step_call_rejects_positional_args_except_hold(self):
        with pytest.raises(VisitError) as exc_info:
            parse('protocol T { Step(tube); }')
        assert "hold(...) is the only positional step form" in str(exc_info.value.orig_exc)

    def test_multiple_protocols(self):
        src = """
        protocol A { let x = 1; }
        protocol B { let y = 2; }
        protocol C { let z = 3; }
        """
        ast = parse(src)
        assert len(ast.protocols) == 3
        assert ast.protocols[0].name == "A"
        assert ast.protocols[1].name == "B"
        assert ast.protocols[2].name == "C"


# ============================================================
# 14. Span metadata
# ============================================================

class TestSpanMetadata:

    def test_span_exists_on_key_nodes(self):
        ast = parse('protocol T { let x = 200uL; Step(v = x); }')
        assert isinstance(ast.span, Span)

        proto = ast.protocols[0]
        assert isinstance(proto.span, Span)

        let_stmt = proto.statements[0]
        assert isinstance(let_stmt.span, Span)
        assert isinstance(let_stmt.value, Quantity)
        assert isinstance(let_stmt.value.span, Span)

        step = proto.statements[1]
        assert isinstance(step.span, Span)
        assert isinstance(step.args[0].span, Span)
        assert isinstance(step.args[0].value, Identifier)
        assert isinstance(step.args[0].value.span, Span)

    def test_parent_span_covers_child_span(self):
        ast = parse('protocol T { let x = (2 + 3) * 4; }')
        let_stmt = ast.protocols[0].statements[0]
        expr = let_stmt.value
        assert isinstance(expr, BinaryOp)
        assert isinstance(expr.span, Span)
        assert isinstance(expr.left, BinaryOp)
        assert isinstance(expr.left.span, Span)

        assert expr.span.start <= expr.left.span.start
        assert expr.span.end >= expr.left.span.end

    def test_span_maps_to_expected_source_snippet(self):
        src = 'protocol T { let x = 200uL; Step(v = x); }'
        ast = parse(src)
        proto = ast.protocols[0]
        let_stmt = proto.statements[0]
        qty = let_stmt.value
        step = proto.statements[1]
        arg = step.args[0]

        assert src[let_stmt.span.start:let_stmt.span.end] == "let x = 200uL"
        assert src[qty.span.start:qty.span.end] == "200uL"
        assert src[step.span.start:step.span.end] == "Step(v = x)"
        assert src[arg.span.start:arg.span.end] == "v = x"

    def test_span_ranges_are_valid(self):
        ast = parse_file(CURRENT_CORE_FIXTURE)
        proto = ast.protocols[0]
        for stmt in proto.statements:
            assert stmt.span.start >= 0
            assert stmt.span.end > stmt.span.start
            if isinstance(stmt, StepCall):
                for arg in stmt.args:
                    assert arg.span.start >= stmt.span.start
                    assert arg.span.end <= stmt.span.end

    def test_repeat_span_exists(self):
        ast = parse('protocol T { repeat 2 { Step(v = 1); } }')
        repeat_stmt = ast.protocols[0].statements[0]
        assert isinstance(repeat_stmt, RepeatStatement)
        assert isinstance(repeat_stmt.span, Span)
        assert isinstance(repeat_stmt.times.span, Span)
        inner = repeat_stmt.statements[0]
        assert isinstance(inner.span, Span)
        assert repeat_stmt.span.start <= inner.span.start
        assert repeat_stmt.span.end >= inner.span.end

    def test_if_span_exists(self):
        ast = parse('protocol T { if true { Step(v = 1); } else { Step(v = 2); } }')
        if_stmt = ast.protocols[0].statements[0]
        assert isinstance(if_stmt, IfStatement)
        assert isinstance(if_stmt.span, Span)
        assert isinstance(if_stmt.condition.span, Span)
        assert isinstance(if_stmt.then_statements[0].span, Span)
        assert isinstance(if_stmt.else_statements[0].span, Span)


# ============================================================
# 15. Invalid input raises errors
# ============================================================

class TestInvalidInput:

    def test_missing_semicolon(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { let x = 5 }')

    def test_missing_closing_brace(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { let x = 5;')

    def test_missing_opening_paren(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { Step source="A"); }')

    def test_missing_closing_paren(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { Step(source="A"; }')

    def test_keyword_as_variable_name(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { let protocol = 5; }')

    def test_keyword_as_protocol_name(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol let { }')

    def test_bare_expression(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { 42; }')

    def test_with_env_rejects_legacy_on_surface(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { with env(thermal = 37C, duration = 1min) on [tube] { hold(sample = tube); } }')

    def test_mutation_rejects_empty_source_list(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { dst << []; }')

    def test_hold_target_accepts_general_expression_surface(self):
        ast = parse('protocol T { with env(thermal = 37C, duration = 1min) { hold(sample = tube(label = "X")); } }')
        stmt = ast.protocols[0].statements[0]
        assert isinstance(stmt, WithEnvStmt)
        assert isinstance(stmt.statements[0], StepCall)

    def test_mutation_rejects_constructor_source_item(self):
        with pytest.raises(UnexpectedInput):
            parse('protocol T { dst << [content(code = "S1", type = "sample"):100uL]; }')
