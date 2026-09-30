"""Agitation contracts and their diagnostic adapter with real values and IR."""

import pytest

from culsma.common.source import Span
from culsma.domains.agitation import AgitationMode, validate_agitation_arguments
from culsma.domains.agitation.contracts import conflicting_arguments, validate_rotation_quantity
from culsma.domains.agitation.validation import validate_agit_contract
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRQuantity, IRStep


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
