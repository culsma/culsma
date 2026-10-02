"""Constraint rules use real domain values without stage objects."""
import pytest
from culsma.domains.constraints import ConstraintRequirement as R
from culsma.domains.constraints import (
    ConstraintRequirementBase, ConstraintRequirementSpec, STANDARD_CONSTRAINT_REQUIREMENTS,
)
from culsma.domains.constraints.rules import ConstraintRules
from culsma.domains.constraints.checks import ColdChainRule, ConstraintContext, ConstraintViolation


class NonfreezingRule:
    @staticmethod
    def validate(context):
        value, unit = context.thermal
        celsius = value - 273.15 if unit == 'K' else value
        if celsius < 0:
            return ConstraintViolation('environment', 'Temperature must not be below 0 C')
        return None


class HandlingRequirement(ConstraintRequirementBase):
    REFRIGERATED = ('refrigerated', ConstraintRequirementSpec(
        category='environmental_protection',
        allowed_on=frozenset({'agit'}),
        scopes=frozenset({'stmt', 'block'}),
        context_checks=(ColdChainRule.validate, NonfreezingRule.validate),
    ))


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


@pytest.mark.parametrize('value', [None, (), (4,), (True, 'C'), ('4', 'C'),
    (float('nan'), 'C'), (float('inf'), 'C'), (4, 'mL'), (4, ['C']), (4, {'unit': 'C'})])
def test_explicit_temperature_must_be_resolved(value):
    assert ConstraintRules.cold_chain_violation(value).kind == 'unresolved'


def test_nested_combination_is_not_a_way_to_bypass_exclusivity():
    assert [v.kind for v in ConstraintRules.combination_violations([R.CUSTOMIZED, R.GENTLE])] == ['customized']


@pytest.mark.parametrize('requirement', [R.COLD_CHAIN, 'cold_chain'])
def test_selected_rule_checks_each_explicit_temperature(requirement):
    contexts = [ConstraintContext(thermal=(4, 'C')), ConstraintContext(thermal=(37, 'C'))]
    violations = ConstraintRules.context_violations([requirement, requirement], contexts)
    assert [v.kind for v in violations] == ['environment']


@pytest.mark.parametrize('requirements', [[], [R.GENTLE], [R.DARK_PROTECTED]])
def test_rules_without_conditions_do_not_resolve_context(requirements):
    def contexts():
        raise AssertionError('No selected rule needs thermal resolution')
        yield

    assert ConstraintRules.context_violations(requirements, contexts()) == []


def test_missing_temperature_does_not_invent_a_cold_chain_condition():
    assert ConstraintRules.context_violations([R.COLD_CHAIN], []) == []


@pytest.mark.parametrize('temperature,expected_messages', [
    ((4, 'C'), []),
    ((-1, 'C'), ['Temperature must not be below 0 C']),
    ((37, 'C'), ["Requirement 'cold_chain' conflicts with env thermal 37C"]),
])
def test_registered_requirement_dispatches_all_its_checks(temperature, expected_messages):
    registry = STANDARD_CONSTRAINT_REQUIREMENTS.with_type(HandlingRequirement, 'test.handling')
    with registry.activate():
        violations = ConstraintRules.context_violations(
            [HandlingRequirement.REFRIGERATED], [ConstraintContext(thermal=temperature)])
    assert [v.message for v in violations] == expected_messages


def test_requirement_spec_freezes_check_iterable_without_consuming_it_twice():
    spec = ConstraintRequirementSpec(
        'environmental_protection', frozenset({'agit'}), frozenset({'stmt'}),
        context_checks=iter([ColdChainRule.validate]),
    )
    assert spec.context_checks == (ColdChainRule.validate,)


def test_requirement_spec_rejects_non_callable_checks():
    with pytest.raises(TypeError, match='checks must be callable'):
        ConstraintRequirementSpec(
            'environmental_protection', frozenset({'agit'}), frozenset({'stmt'}),
            context_checks=('ColdChainRule.validate',),
        )
