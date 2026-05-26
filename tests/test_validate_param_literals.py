from __future__ import annotations

from culsma.pipeline.ir_nodes import IRBoolean, IRList, IRParam, IRQuantity, IRString
from culsma.pipeline.validate.validator import literal_param_bindings, literal_param_value


def test_literal_param_value_public_helper_accepts_plan_binding_literals():
    assert literal_param_value(IRString("schema-A")) == "schema-A"
    assert literal_param_value(IRBoolean(True)) is True
    assert literal_param_value(IRQuantity(3, None)) == 3.0
    assert literal_param_value(IRQuantity(3, "min")) is None
    assert literal_param_value(IRList([IRString("a"), IRString("b")])) == ["a", "b"]


def test_literal_param_bindings_public_helper_filters_non_literal_defaults():
    params = [
        IRParam(name="schema", default=IRString("schema-A")),
        IRParam(name="duration", default=IRQuantity(3, "min")),
        IRParam(name="flag", default=IRBoolean(False)),
    ]

    assert literal_param_bindings(params) == {"schema": "schema-A", "flag": False}
