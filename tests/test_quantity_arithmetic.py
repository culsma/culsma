"""Exercise the public quantity arithmetic API independently of the compiler."""

import pytest

from culsma.common.quantity_arithmetic import (
    QuantityArithmeticError,
    convert_value,
    quantity_binary,
    quantity_parts,
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


@pytest.mark.parametrize('op,left,right,expected', [
    ('+', (1, 'L'), (250, 'mL'), (1.25, 'L')),
    ('-', (500, 'ug'), (1, 'mg'), (-500, 'ug')),
    ('+', (1, 'h'), (30, 'min'), (1.5, 'h')),
    ('/', (2, 'min'), (500, 'ms'), 240),
    ('/', (1, 'A'), (250, 'mA'), 4),
    ('+', (1, 'Hz'), (60, 'cycle/min'), (2, 'Hz')),
    ('-', (300, 'K'), (275, 'K'), (25, 'K')),
    ('*', -2, (3, 'mL'), (-6, 'mL')),
    ('/', (0, 'mL'), 2, (0, 'mL')),
    ('/', 6, 4, 1.5),
])
def test_arithmetic_preserves_units_and_converts_before_calculating(op, left, right, expected):
    result = quantity_binary(op, left, right)
    if isinstance(expected, tuple):
        assert result[0] == pytest.approx(expected[0])
        assert result[1] == expected[1]
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize('op,left,right,reason', [
    ('+', 1, (1, 'mL'), 'dimension'),
    ('-', (1, 'mL'), 1, 'dimension'),
    ('+', (1, 'mg'), (1, 's'), 'dimension'),
    ('*', (1, 'mL'), (1, 'mg'), 'dimension'),
    ('/', 1, (1, 'mL'), 'dimension'),
    ('/', (1, 'mL'), (1, 'mg'), 'dimension'),
    ('+', (20, 'C'), (300, 'K'), 'dimension'),
    ('/', (20, 'C'), (300, 'K'), 'dimension'),
    ('%', 4, 2, 'operand'),
    ('/', (1, 'mL'), 0, 'zero'),
    ('/', (1, 'mL'), (0, 'uL'), 'zero'),
    ('/', (1, 'L'), (5e-324, 'uL'), 'nonfinite'),
    ('*', (1e308, 'mL'), 10, 'nonfinite'),
    ('+', True, 1, 'operand'),
    ('+', (1, 'unknown'), (1, 'mL'), 'unit'),
    ('+', (1, None), 1, 'unit'),
])
def test_invalid_arithmetic_exposes_stable_error_reason(op, left, right, reason):
    with pytest.raises(QuantityArithmeticError) as caught:
        quantity_binary(op, left, right)
    assert caught.value.reason == reason


@pytest.mark.parametrize('value,source,target,reason', [
    (1, 'unknown', 'uL', 'unit'),
    (1, 'uL', 'unknown', 'unit'),
    (1, 'mL', 'mg', 'dimension'),
    (20, 'C', 'K', 'dimension'),
    (float('inf'), 'mL', 'mL', 'nonfinite'),
    (1e308, 'L', 'uL', 'nonfinite'),
])
def test_invalid_conversion_exposes_stable_error_reason(value, source, target, reason):
    with pytest.raises(QuantityArithmeticError) as caught:
        convert_value(value, source, target)
    assert caught.value.reason == reason


@pytest.mark.parametrize('value,expected', [(0, (0, None)), (-2.5, (-2.5, None)), ((3, 'uL'), (3, 'uL'))])
def test_quantity_parts_preserves_scalar_and_unit(value, expected):
    assert quantity_parts(value) == expected
