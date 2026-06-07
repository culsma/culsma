"""Lark transformer adapter: routes parse-tree callbacks into rule handlers."""

from __future__ import annotations

from lark import Transformer, v_args

from culsma.parser.transformer_rules import (
    ParseRuleContext,
    ParseRuleDispatcher,
    create_parse_rule_dispatcher,
)


@v_args(meta=True)
class CulsmaTransformer(Transformer):
    """Transform a Lark parse tree into a Culsma AST."""

    def __init__(
        self,
        dispatcher: ParseRuleDispatcher | None = None,
        context: ParseRuleContext | None = None,
    ) -> None:
        super().__init__()
        self._dispatcher = dispatcher or create_parse_rule_dispatcher()
        self._context = context or ParseRuleContext()

    def _dispatch(self, rule_name: str, meta, items):
        return self._dispatcher.dispatch(rule_name, meta, list(items), self._context)

    def start(self, meta, items):
        return self._dispatch("start", meta, items)

    def source_include_decl(self, meta, items):
        return self._dispatch("source_include_decl", meta, items)

    def library_import_decl(self, meta, items):
        return self._dispatch("library_import_decl", meta, items)

    def protocol_decl(self, meta, items):
        return self._dispatch("protocol_decl", meta, items)

    def param_decl_list(self, meta, items):
        return self._dispatch("param_decl_list", meta, items)

    def param_decl(self, meta, items):
        return self._dispatch("param_decl", meta, items)

    def returns_decl(self, meta, items):
        return self._dispatch("returns_decl", meta, items)

    def return_name_list(self, meta, items):
        return self._dispatch("return_name_list", meta, items)

    def statement(self, meta, items):
        return self._dispatch("statement", meta, items)

    def include_stmt(self, meta, items):
        return self._dispatch("include_stmt", meta, items)

    def let_statement(self, meta, items):
        return self._dispatch("let_statement", meta, items)

    def return_statement(self, meta, items):
        return self._dispatch("return_statement", meta, items)

    def named_return_binding(self, meta, items):
        return self._dispatch("named_return_binding", meta, items)

    def named_return_binding_list(self, meta, items):
        return self._dispatch("named_return_binding_list", meta, items)

    def named_return_statement(self, meta, items):
        return self._dispatch("named_return_statement", meta, items)

    def assign_identifier_statement(self, meta, items):
        return self._dispatch("assign_identifier_statement", meta, items)

    def assign_member_statement(self, meta, items):
        return self._dispatch("assign_member_statement", meta, items)

    def call_statement_arg_list(self, meta, items):
        return self._dispatch("call_statement_arg_list", meta, items)

    def call_statement(self, meta, items):
        return self._dispatch("call_statement", meta, items)

    def method_call_statement(self, meta, items):
        return self._dispatch("method_call_statement", meta, items)

    def step_call(self, meta, items):
        return self._dispatch("step_call", meta, items)

    def env_arg_block(self, meta, items):
        return self._dispatch("env_arg_block", meta, items)

    def constraint_item_block(self, meta, items):
        return self._dispatch("constraint_item_block", meta, items)

    def constraint_item_list(self, meta, items):
        return self._dispatch("constraint_item_list", meta, items)

    def constraint_name(self, meta, items):
        return self._dispatch("constraint_name", meta, items)

    def mutation_source_list(self, meta, items):
        return self._dispatch("mutation_source_list", meta, items)

    def with_env_stmt(self, meta, items):
        return self._dispatch("with_env_stmt", meta, items)

    def with_constraint_stmt(self, meta, items):
        return self._dispatch("with_constraint_stmt", meta, items)

    def constrained_simple_statement(self, meta, items):
        return self._dispatch("constrained_simple_statement", meta, items)

    def mutation_stmt(self, meta, items):
        return self._dispatch("mutation_stmt", meta, items)

    def break_stmt(self, meta, items):
        return self._dispatch("break_stmt", meta, items)

    def continue_stmt(self, meta, items):
        return self._dispatch("continue_stmt", meta, items)

    def repeat_binding_header(self, meta, items):
        return self._dispatch("repeat_binding_header", meta, items)

    def repeat_times_header(self, meta, items):
        return self._dispatch("repeat_times_header", meta, items)

    def repeat_statement(self, meta, items):
        return self._dispatch("repeat_statement", meta, items)

    def else_clause(self, meta, items):
        return self._dispatch("else_clause", meta, items)

    def if_statement(self, meta, items):
        return self._dispatch("if_statement", meta, items)

    def arg_list(self, meta, items):
        return self._dispatch("arg_list", meta, items)

    def step_arg_list(self, meta, items):
        return self._dispatch("step_arg_list", meta, items)

    def arg(self, meta, items):
        return self._dispatch("arg", meta, items)

    def or_op(self, meta, items):
        return self._dispatch("or_op", meta, items)

    def and_op(self, meta, items):
        return self._dispatch("and_op", meta, items)

    def comparison(self, meta, items):
        return self._dispatch("comparison", meta, items)

    def add_op(self, meta, items):
        return self._dispatch("add_op", meta, items)

    def sub_op(self, meta, items):
        return self._dispatch("sub_op", meta, items)

    def mul_op(self, meta, items):
        return self._dispatch("mul_op", meta, items)

    def div_op(self, meta, items):
        return self._dispatch("div_op", meta, items)

    def neg_op(self, meta, items):
        return self._dispatch("neg_op", meta, items)

    def quantity(self, meta, items):
        return self._dispatch("quantity", meta, items)

    def string_literal(self, meta, items):
        return self._dispatch("string_literal", meta, items)

    def boolean_literal(self, meta, items):
        return self._dispatch("boolean_literal", meta, items)

    def identifier_ref(self, meta, items):
        return self._dispatch("identifier_ref", meta, items)

    def list_literal(self, meta, items):
        return self._dispatch("list_literal", meta, items)

    def record_key_identifier(self, meta, items):
        return self._dispatch("record_key_identifier", meta, items)

    def record_key_string(self, meta, items):
        return self._dispatch("record_key_string", meta, items)

    def record_item(self, meta, items):
        return self._dispatch("record_item", meta, items)

    def record_literal(self, meta, items):
        return self._dispatch("record_literal", meta, items)

    def group_expr(self, meta, items):
        return self._dispatch("group_expr", meta, items)

    def selector_region(self, meta, items):
        return self._dispatch("selector_region", meta, items)

    def plate_selector_expr(self, meta, items):
        return self._dispatch("plate_selector_expr", meta, items)

    def call_expr(self, meta, items):
        return self._dispatch("call_expr", meta, items)

    def method_call_arg_list(self, meta, items):
        return self._dispatch("method_call_arg_list", meta, items)

    def markers_expr(self, meta, items):
        return self._dispatch("markers_expr", meta, items)

    def index_expr(self, meta, items):
        return self._dispatch("index_expr", meta, items)

    def member_expr(self, meta, items):
        return self._dispatch("member_expr", meta, items)

    def method_call_expr(self, meta, items):
        return self._dispatch("method_call_expr", meta, items)

    def pair_expr(self, meta, items):
        return self._dispatch("pair_expr", meta, items)

    def mutation_series_expr(self, meta, items):
        return self._dispatch("mutation_series_expr", meta, items)
