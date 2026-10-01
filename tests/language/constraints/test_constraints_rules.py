"""Constraint rules use real domain values without stage objects."""
import pytest
from culsma.domains.constraints import ConstraintRequirement as R
from culsma.domains.constraints.rules import ConstraintRules


@pytest.mark.parametrize('requirement', list(R))
def test_standard_spelling_has_same_applicability_as_enum(requirement):
    assert ConstraintRules.applicability_violations('agit', [requirement.value]) == \
        ConstraintRules.applicability_violations('agit', [requirement])


@pytest.mark.parametrize('spelling', ['GENTLE', ' gentle', 'gentel', 'extension.gentle'])
def test_unknown_spelling_is_rejected_without_fallback(spelling):
    assert [v.kind for v in ConstraintRules.applicability_violations('agit', [spelling])] == ['unknown']


@pytest.mark.parametrize('requirement', [R.GENTLE, R.ASEPTIC, R.CROSS_CONTAM_CONTROL,
                                       R.COLD_CHAIN, R.DARK_PROTECTED, R.CONTROLLED_ATMOSPHERE])
def test_agitation_protection_requirements(requirement):
    assert not ConstraintRules.applicability_violations('agit', [requirement])


@pytest.mark.parametrize('requirement', [R.DROPWISE, R.SPREAD, R.SEALED, R.PRESERVE_LAYERING])
def test_agitation_keeps_unaccepted_requirements_rejected(requirement):
    assert [v.kind for v in ConstraintRules.applicability_violations('agit', [requirement])] == ['family']


@pytest.mark.parametrize('value,conflict', [((4, 'C'), False), ((8, 'C'), False),
    ((277.15, 'K'), False), ((281.15, 'K'), False), ((37, 'C'), True), ((310.15, 'K'), True)])
def test_cold_chain_units(value, conflict):
    violation = ConstraintRules.cold_chain_violation(value)
    assert (violation is not None) == conflict
    if violation:
        assert violation.kind == 'environment'


@pytest.mark.parametrize('value', [None, (float('nan'), 'C'), (4, 'mL')])
def test_explicit_temperature_must_be_resolved(value):
    assert ConstraintRules.cold_chain_violation(value).kind == 'unresolved'


def test_nested_combination_is_not_a_way_to_bypass_exclusivity():
    assert [v.kind for v in ConstraintRules.combination_violations([R.CUSTOMIZED, R.GENTLE])] == ['customized']
