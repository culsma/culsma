"""Exercise the public quantity arithmetic API independently of the compiler."""

import pytest

from culsma.common.quantity_arithmetic import (
    QuantityArithmeticError,
    convert_value,
    quantity_binary,
    quantity_result_unit,
    require_finite_number,
)
from culsma.runtime.state import RuntimeState
from culsma.runtime.values import UNRESOLVED, evaluate_runtime_expression


@pytest.mark.parametrize('value,source,target,expected', [
    (1, 'mL', 'uL', 1000), (1000, 'ug', 'mg', 1),
    (2, 'min', 's', 120), (1, 'V', 'mV', 1000),
    (1, 'A', 'uA', 1000000), (20, 'pct', '%', 20),
])
def test_convert_compatible_units(value, source, target, expected):
    assert convert_value(value, source, target) == pytest.approx(expected)


@pytest.mark.parametrize('op,left,right,unit', [
    ('/', 'mL', None, 'mL'), ('/', 'mL', 'uL', None),
    ('*', None, 'mg', 'mg'), ('+', 'mL', 'uL', 'mL'),
    ('-', 'uL', 'mL', 'uL'), ('*', None, None, None),
])
def test_unit_inference_needs_no_assumed_values(op, left, right, unit):
    assert quantity_result_unit(op, left, right) == unit


@pytest.mark.parametrize('value', [10**400, float('inf'), float('nan')])
def test_nonrepresentable_numbers_raise_domain_error(value):
    with pytest.raises(QuantityArithmeticError) as caught:
        require_finite_number(value)
    assert caught.value.reason == 'nonfinite'


def test_integer_overflow_is_rejected_without_python_exception():
    with pytest.raises(QuantityArithmeticError) as caught:
        quantity_binary('*', 10**200, 10**200)
    assert caught.value.reason == 'nonfinite'
    expr = {'kind': 'IRBinary', 'op': '*', 'left': 10**200, 'right': 10**200}
    assert evaluate_runtime_expression(expr, RuntimeState()) is UNRESOLVED


@pytest.mark.parametrize('value', [True, '10', (1, 'mL')])
def test_non_numeric_scalars_are_rejected(value):
    with pytest.raises(QuantityArithmeticError) as caught:
        require_finite_number(value)
    assert caught.value.reason == 'operand'
