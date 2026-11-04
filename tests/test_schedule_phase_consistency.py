"""The same schedule must retain its boundaries at compile time and plan time.

Compile-time literals and late-bound protocol parameters use separate evaluators.
These independent expected results guard against drift between those paths.
"""

import re

import pytest

from culsma.parser.ast_nodes import Arg, CallExpr, ListLiteral, Quantity, StringLiteral
from culsma.pipeline.compile.context import BlockContext
from culsma.pipeline.compile.schedule import ScheduleEvaluator
from culsma.pipeline.plan.static_eval import PlanStaticEvaluator


def q(value, unit=None):
    return Quantity(value=value, unit=unit)


def points(*values):
    return ListLiteral(elements=list(values))


def serialize(expr):
    if isinstance(expr, Quantity):
        return {'kind': 'IRQuantity', 'value': expr.value, 'unit': expr.unit}
    if isinstance(expr, ListLiteral):
        return {'kind': 'IRList', 'elements': [serialize(item) for item in expr.elements]}
    if isinstance(expr, StringLiteral):
        return {'kind': 'IRString', 'value': expr.value}
    raise AssertionError(f'Unsupported test expression: {expr!r}')


def evaluate(phase, args, *, continuous=False, boundary=None):
    if phase == 'compile':
        schedule = CallExpr(name='schedule', args=[Arg(name=k, value=v) for k, v in args.items()])
        evaluator = ScheduleEvaluator()
        ctx = BlockContext(scope_id='p0', env_time_boundary=boundary)
        if continuous:
            result = evaluator.eval_continuous_schedule_boundary(schedule, ctx=ctx)
            return result.value, result.unit
        result = evaluator.eval_schedule_points(schedule, ctx=ctx)
        return [(item.value, item.unit) for item in result]
    schedule = {'kind': 'IRCall', 'name': 'schedule',
                'args': [{'name': k, 'value': serialize(v)} for k, v in args.items()]}
    evaluator = PlanStaticEvaluator()
    kwargs = {'env_time_boundary': serialize(boundary) if boundary is not None else None}
    if continuous:
        result = evaluator.eval_continuous_schedule_boundary(schedule, **kwargs)
        return result['value'], result['unit']
    result = evaluator.eval_discrete_schedule_points(schedule, **kwargs)
    return [(item['value'], item['unit']) for item in result]


@pytest.fixture(params=['compile', 'plan'])
def phase(request):
    return request.param


@pytest.mark.parametrize('args,boundary,expected', [
    ({'start': q(1), 'end': q(5), 'step': q(2)}, None, [(1, None), (3, None), (5, None)]),
    ({'start': q(1), 'end': q(4), 'step': q(2)}, None, [(1, None), (3, None)]),
    ({'start': q(3), 'end': q(3), 'step': q(1)}, None, [(3, None)]),
    ({'start': q(3), 'end': q(2), 'step': q(1)}, None, []),
    ({'start': q(0, 'min'), 'end': q(90, 's'), 'step': q(30, 's')}, None,
     [(0, 'min'), (.5, 'min'), (1, 'min'), (1.5, 'min')]),
    ({'start': q(0, 's'), 'end': q(.3, 's'), 'step': q(100, 'ms')}, None,
     [(0, 's'), (.1, 's'), (.2, 's'), (.3, 's')]),
    ({'start': q(0, 'min'), 'step': q(30, 's')}, q(1, 'min'),
     [(0, 'min'), (.5, 'min'), (1, 'min')]),
    ({'start': q(2, 'min'), 'end': q(1, 'min'), 'step': q(1, 's')}, None, []),
    ({'at': points(q(0, 's'), q(1, 'min'))}, q(60, 's'), [(0, 's'), (1, 'min')]),
])
def test_discrete_schedule_boundaries(phase, args, boundary, expected):
    actual = evaluate(phase, args, boundary=boundary)
    assert len(actual) == len(expected)
    for (value, unit), (expected_value, expected_unit) in zip(actual, expected):
        assert value == pytest.approx(expected_value)
        assert unit == expected_unit


@pytest.mark.parametrize('args,boundary,message', [
    ({}, None, 'must use either'),
    ({'at': points(q(1)), 'start': q(1)}, None, 'must use either'),
    ({'at': points()}, None, 'non-empty list'),
    ({'at': points(q(1, 's'), q(2))}, None, 'consistent types'),
    ({'at': points(q(1), q(2, 's'))}, None, 'consistent types'),
    ({'at': points(q(1.5))}, None, 'supports only'),
    ({'at': points(q(1, 'mL'))}, None, 'supports only'),
    ({'at': points(q(61, 's'))}, q(1, 'min'), 'exceeds enclosing env boundary'),
    ({'start': q(1)}, None, 'requires start and step'),
    ({'start': q(1), 'step': q(1)}, None, 'requires explicit end'),
    ({'start': q(0, 's'), 'step': q(1, 's')}, None, 'requires enclosing env boundary'),
    ({'start': q(0), 'end': q(3), 'step': q(0)}, None, 'count step must be > 0'),
    ({'start': q(0), 'end': q(3), 'step': q(-1)}, None, 'count step must be > 0'),
    ({'start': q(0, 's'), 'end': q(3, 's'), 'step': q(0, 's')}, None, 'time step must be > 0'),
    ({'start': q(0, 's'), 'end': q(3, 's'), 'step': q(-1, 's')}, None, 'time step must be > 0'),
    ({'start': q(0), 'end': q(3.5), 'step': q(1)}, None, 'consistent'),
    ({'start': q(0, 's'), 'end': q(3), 'step': q(1, 's')}, None, 'consistent'),
    ({'start': q(0, 's'), 'end': q(3, 's'), 'step': q(1)}, None, 'consistent'),
    ({'start': q(0, 's'), 'end': q(61, 's'), 'step': q(1, 's')}, q(1, 'min'),
     'exceeds enclosing env boundary'),
    ({'start': q(0), 'end': q(3), 'step': q(1), 'duration': q(1, 's')}, None, 'does not allow'),
    ({'at': points(q(1)), 'mode': StringLiteral('unknown')}, None, 'schedule mode'),
])
def test_invalid_discrete_schedule_has_controlled_failure(phase, args, boundary, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        evaluate(phase, args, boundary=boundary)


@pytest.mark.parametrize('args,boundary,expected', [
    ({'start': q(1, 'min'), 'end': q(90, 's')}, None, (.5, 'min')),
    ({'start': q(1, 'min'), 'end': q(60, 's')}, None, (0, 'min')),
    ({'start': q(0, 's'), 'duration': q(1, 'min')}, q(60, 's'), (1, 'min')),
])
def test_continuous_schedule_window(phase, args, boundary, expected):
    value, unit = evaluate(phase, {**args, 'mode': StringLiteral('continuous')},
                           continuous=True, boundary=boundary)
    assert value == pytest.approx(expected[0])
    assert unit == expected[1]


@pytest.mark.parametrize('args,boundary,message', [
    ({'start': q(0, 's'), 'duration': q(1, 's'), 'step': q(1, 's')}, None, 'does not allow at or step'),
    ({'start': q(0), 'duration': q(1, 's')}, None, 'requires time-valued start'),
    ({'start': q(0, 's')}, None, 'requires end or duration'),
    ({'start': q(0, 's'), 'end': q(1, 's'), 'duration': q(1, 's')}, None, 'must not use both'),
    ({'start': q(0, 's'), 'duration': q(1)}, None, 'duration must be a time quantity'),
    ({'start': q(0, 's'), 'end': q(1)}, None, 'end must be a time quantity'),
    ({'start': q(1, 'min'), 'end': q(59, 's')}, None, 'end must be >= start'),
    ({'start': q(0, 's'), 'duration': q(61, 's')}, q(1, 'min'), 'exceeds enclosing boundary'),
])
def test_invalid_continuous_schedule_has_controlled_failure(phase, args, boundary, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        evaluate(phase, {**args, 'mode': StringLiteral('continuous')}, continuous=True, boundary=boundary)
