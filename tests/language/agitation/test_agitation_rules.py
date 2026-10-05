"""Agitation contracts and their diagnostic adapter with real values and IR."""

import pytest

from culsma.common.source import Span
from culsma.domains.agitation import AgitationMode, validate_agitation_arguments
from culsma.domains.agitation.contracts import conflicting_arguments, validate_rotation_quantity
from culsma.domains.agitation.validation import validate_agit_contract, validate_motion
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRMember, IRQuantity, IRStep


@pytest.mark.parametrize("mode,present,conflicts", [
    (AgitationMode.FLICK, set(), ()),
    (AgitationMode.FLICK, {"cycles"}, ()),
    (AgitationMode.FLICK, {"duration", "rate"}, ("duration", "rate")),
    (AgitationMode.INVERT, {"rate"}, ("rate",)),
    (AgitationMode.INVERT, {"cycles"}, ()),
    (AgitationMode.SHAKE, {"duration", "rate"}, ()),
    (AgitationMode.SHAKE, {"cycles"}, ("cycles",)),
    (AgitationMode.STIR, {"cycles"}, ("cycles",)),
    (AgitationMode.VORTEX, {"duration"}, ()),
    (AgitationMode.VORTEX, {"cycles"}, ("cycles",)),
])
def test_agitation_argument_contract(mode, present, conflicts):
    assert conflicting_arguments(mode, present) == conflicts
    kwargs = dict(has_duration="duration" in present, has_rate="rate" in present,
                  has_cycles="cycles" in present)
    if conflicts:
        message = ("invert/flick forbid duration and rate; use cycles"
                   if mode in {AgitationMode.INVERT, AgitationMode.FLICK}
                   else "cycles is only allowed for invert/flick")
        with pytest.raises(ValueError, match=message):
            validate_agitation_arguments(mode, **kwargs)
    else:
        assert validate_agitation_arguments(mode, **kwargs) is mode


def test_agitation_conflicts_preserve_each_argument_location():
    duration_span = Span(2, 4, 10, 13)
    rate_span = Span(3, 4, 20, 25)
    step = IRStep("mix", "agit", [
        IRArg("mode", IRIdentifier("flick")),
        IRArg("duration", IRQuantity(3, "s"), duration_span),
        IRArg("rate", IRQuantity(60, "rpm"), rate_span),
    ])
    diagnostics = validate_agit_contract(step, literal_bindings={})
    assert [(d.code, d.message, d.span, d.node_id) for d in diagnostics] == [
        ("SEM_AGIT_ARG_CONFLICT", "agit(mode = flick): duration is not allowed; use cycles", duration_span, "mix"),
        ("SEM_AGIT_ARG_CONFLICT", "agit(mode = flick): rate is not allowed; use cycles", rate_span, "mix"),
    ]


@pytest.mark.parametrize('name,value', [('duration', (2, 'h')), ('rate', (20, 'rpm'))])
def test_rotation_quantity_contract_accepts_shared_values(name, value):
    validate_rotation_quantity(name, value)


@pytest.mark.parametrize('value,message', [
    ((0, 's'), 'finite and positive'),
    ((-1, 's'), 'finite and positive'),
    ((float('inf'), 's'), 'finite and positive'),
    ((float('nan'), 's'), 'finite and positive'),
    ((True, 's'), 'finite and positive'),
    ((2, 'mL'), 'dimension time'),
    (2, 'unit-bearing quantity'),
])
def test_rotation_quantity_contract_rejects_invalid_values(value, message):
    with pytest.raises(ValueError, match=message):
        validate_rotation_quantity('duration', value)


@pytest.mark.parametrize('motion,amount,rate', [
    ('LINEAR', IRArg('duration', IRQuantity(5, 's')), IRQuantity(2, 'Hz')),
    ('ORBITAL', IRArg('duration', IRQuantity(5, 's')), IRQuantity(60, 'rpm')),
    ('ROCK', IRArg('cycles', IRQuantity(4, None)), IRQuantity(30, 'cycle/min')),
    ('ROCK', IRArg('duration', IRQuantity(5, 's')), IRQuantity(2, 'Hz')),
    ('ROTATION', IRArg('duration', IRQuantity(5, 's')), IRQuantity(60, 'rpm')),
])
def test_validate_motion_accepts_typed_motion_and_compatible_quantities(motion, amount, rate):
    motion_arg = IRArg('motion', IRMember(IRIdentifier('ShakeMotion'), motion))
    step = IRStep('mix', 'agit', [motion_arg, amount, IRArg('rate', rate)])
    assert validate_motion(step, AgitationMode.SHAKE, motion_arg, {}, frozenset()) == []


@pytest.mark.parametrize('mode,motion,code,message', [
    (AgitationMode.ROTATION, 'rotation', 'SEM_AGIT_ARG_CONFLICT',
     'motion is only allowed with mode=shake'),
    (AgitationMode.SHAKE, 'swirl', 'SEM_AGIT_MOTION_UNKNOWN',
     'shake motion must be linear, orbital, rock or rotation'),
])
@pytest.mark.parametrize('explicit_span', [False, True])
def test_validate_motion_reports_identity_errors_at_argument_or_step(mode, motion, code, message, explicit_span):
    step_span = Span(1, 1, 1, 50)
    arg_span = Span(1, 20, 1, 35) if explicit_span else None
    motion_arg = IRArg('motion', IRIdentifier(motion), arg_span)
    step = IRStep('mix', 'agit', [motion_arg], span=step_span)
    diagnostics = validate_motion(step, mode, motion_arg, {}, frozenset())
    assert [(d.code, d.message, d.span, d.node_id) for d in diagnostics] == [
        (code, message, arg_span or step_span, 'mix'),
    ]


@pytest.mark.parametrize('motion,arguments,expected', [
    ('rock', [], [('SEM_AGIT_DURATION_REQUIRED', 'motion')]),
    ('rock', [IRArg('duration', IRQuantity(5, 's')), IRArg('cycles', IRQuantity(4, None))],
     [('SEM_AGIT_ARG_CONFLICT', 'cycles')]),
    ('linear', [IRArg('cycles', IRQuantity(4, None))],
     [('SEM_AGIT_DURATION_REQUIRED', 'motion'), ('SEM_AGIT_ARG_CONFLICT', 'cycles')]),
    ('orbital', [IRArg('duration', IRQuantity(0, 's')), IRArg('rate', IRQuantity(2, 'Hz'))],
     [('SEM_AGIT_QUANTITY_INVALID', 'duration'), ('SEM_AGIT_QUANTITY_INVALID', 'rate')]),
    ('rock', [IRArg('cycles', IRQuantity(1.5, None))],
     [('SEM_AGIT_QUANTITY_INVALID', 'cycles')]),
])
def test_validate_motion_maps_contract_failures_to_each_argument(motion, arguments, expected):
    motion_arg = IRArg('motion', IRIdentifier(motion), Span(1, 1, 1, 10))
    args = [motion_arg] + [
        IRArg(arg.name, arg.value, Span(i, 1, i, 10))
        for i, arg in enumerate(arguments, start=2)
    ]
    step = IRStep('mix', 'agit', args)
    diagnostics = validate_motion(step, AgitationMode.SHAKE, motion_arg, {}, frozenset())
    spans = {arg.name: arg.span for arg in args}
    assert [(d.code, d.span, d.node_id) for d in diagnostics] == [
        (code, spans[name], 'mix') for code, name in expected
    ]


def test_validate_motion_resolves_motion_and_quantity_binding_chains():
    motion_arg = IRArg('motion', IRIdentifier('trajectory'))
    rate_span = Span(2, 1, 2, 20)
    step = IRStep('mix', 'agit', [motion_arg, IRArg('duration', IRQuantity(5, 's')),
                                IRArg('rate', IRIdentifier('speed'), rate_span)])
    bindings = {'trajectory': IRIdentifier('kind'), 'kind': IRIdentifier('linear'),
                'speed': IRIdentifier('frequency'), 'frequency': IRQuantity(20, 'rpm')}
    diagnostics = validate_motion(step, AgitationMode.SHAKE, motion_arg, bindings, frozenset())
    assert [(d.code, d.message, d.span) for d in diagnostics] == [
        ('SEM_AGIT_QUANTITY_INVALID', 'linear rate must have dimension frequency', rate_span),
    ]


@pytest.mark.parametrize('motion,bindings,defined_names', [
    (IRIdentifier('trajectory'), {}, {'trajectory'}),
    (IRIdentifier('a'), {'a': IRIdentifier('b'), 'b': IRIdentifier('a')}, set()),
    (IRMember(IRIdentifier('AgitationMode'), 'ROTATION'), {}, set()),
])
def test_validate_motion_leaves_deferred_and_type_binding_errors_to_owning_stages(motion, bindings, defined_names):
    motion_arg = IRArg('motion', motion)
    step = IRStep('mix', 'agit', [motion_arg])
    assert validate_motion(step, AgitationMode.SHAKE, motion_arg, bindings, defined_names) == []


def test_validate_motion_defers_unresolved_quantity_values():
    motion_arg = IRArg('motion', IRIdentifier('linear'))
    step = IRStep('mix', 'agit', [motion_arg, IRArg('duration', IRIdentifier('elapsed'))])
    assert validate_motion(step, AgitationMode.SHAKE, motion_arg, {}, {'elapsed'}) == []
