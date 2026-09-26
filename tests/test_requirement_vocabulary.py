import json
import pytest
from culsma.domains.constraints import (
    ConstraintRequirement, ConstraintRequirementBase, RequirementSpec,
    STANDARD_CONSTRAINT_REQUIREMENTS,
)
from culsma.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver


class LabRequirement(ConstraintRequirementBase):
    TRACEABLE=('lab_traceable', RequirementSpec('traceability', frozenset({'mutation'}), frozenset({'block','stmt'})))


def registry():
    return STANDARD_CONSTRAINT_REQUIREMENTS.with_type(LabRequirement,'example.requirement')


def prepare(requirement):
    source=f'''protocol T {{
        let a=tube(load=[content(kind=formulation,type=medium,code="M"):1mL]);
        let b=tube();
        b << [a:1uL] with constraint({requirement});
    }}'''
    compiled=compile_ast(resolve_program(parse(source)).prepared_program)
    semantic=validate(compiled.ir,analysis=compiled.analysis,enforce_binding=True)
    return compiled,semantic


@pytest.mark.parametrize('requirement',['high_precision','ConstraintRequirement.HIGH_PRECISION'])
def test_standard_requirements_keep_behavior(requirement):
    compiled,semantic=prepare(requirement)
    assert semantic.ok, semantic.diagnostics
    plan=lower_ir_to_plan(compiled.ir)
    result=run(plan=plan,driver=StubDriver(supported_requirements={'high_precision'}))
    assert result.ok, result.diagnostics
    json.dumps(plan.to_dict())


def test_extension_requires_qualified_member_and_explicit_execution_support():
    with registry().activate():
        _,semantic=prepare('lab_traceable')
        assert 'SEM_UNKNOWN_REQUIREMENT' in [d.code for d in semantic.diagnostics]
        compiled,semantic=prepare('LabRequirement.TRACEABLE')
        assert semantic.ok, semantic.diagnostics
        plan=lower_ir_to_plan(compiled.ir)
        rejected=run(plan=plan,driver=StubDriver())
        assert not rejected.ok
        assert 'RT_DRIVER_REQUIREMENT_UNSUPPORTED' in [d.code for d in rejected.diagnostics]
        class Supported(StubDriver):
            supported_requirement_types=frozenset({('example.requirement',1)})
        result=run(plan=plan,driver=Supported())
        assert result.ok, result.diagnostics
        json.dumps(plan.to_dict())
    assert not run(plan=plan,driver=Supported()).ok


def test_unknown_and_foreign_members_keep_requirement_diagnostics():
    for value in ('ConstraintRequirement.TYPO','ObservationUnit.SINGLE_CELL'):
        _,semantic=prepare(value)
        assert 'SEM_UNKNOWN_REQUIREMENT' in [d.code for d in semantic.diagnostics]


def test_standard_application_rules_are_unchanged_for_typed_members():
    _,semantic=prepare('ConstraintRequirement.SEALED')
    assert not semantic.ok
    with pytest.raises(ValueError):
        RequirementSpec('invalid',frozenset({'unknown_operation'}),frozenset({'block'}))


def test_requirement_extension_survives_json_reload():
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
    with registry().activate():
        compiled,semantic=prepare('LabRequirement.TRACEABLE')
        assert semantic.ok
        plan=lower_ir_to_plan(compiled.ir)
        payload=json.loads(json.dumps(plan.to_dict()))['plans'][0]
        loaded=PlanProgram(plans=[ProtocolPlan(payload['protocol_id'],payload['protocol_name'],steps=[
            PlanStep(s['step_id'],s['op'],s['args'],s['deps'],s['gate']) for s in payload['steps']])])
        class Supported(StubDriver):
            supported_requirement_types=frozenset({('example.requirement',1)})
        result=run(plan=loaded,driver=Supported())
        assert result.ok, result.diagnostics
    assert not run(plan=loaded,driver=Supported()).ok


def test_unsupported_context_predicates_are_not_silently_ignored():
    with pytest.raises(ValueError,match='context predicates'):
        RequirementSpec('custom',frozenset({'mutation'}),frozenset({'block'}),needs_context=frozenset({'unimplemented'}))
