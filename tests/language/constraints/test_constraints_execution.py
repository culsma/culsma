"""Source-to-driver constraint gates, scope restoration and runtime binding."""
import pytest
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.runtime.executor import run


class RecordingDriver(StubDriver):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.actions = []

    def execute(self, step):
        if step.op in {'agit', 'Mutation', 'env_hold'}:
            self.actions.append(step)
        return super().execute(step)


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    return compiled, validate(compiled.ir, analysis=compiled.analysis)


def plan_source(source):
    compiled, semantic = compile_source(source)
    assert semantic.ok, semantic.diagnostics
    assert typecheck(compiled.ir, analysis=compiled.analysis).ok
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    return plan


@pytest.mark.parametrize('requirement', ['GENTLE', 'ASEPTIC', 'CROSS_CONTAM_CONTROL',
                                      'COLD_CHAIN', 'DARK_PROTECTED', 'CONTROLLED_ATMOSPHERE'])
def test_source_enum_requirement_reaches_agitation_driver(requirement):
    plan = plan_source(f'''
let sample=tube(label="S",capacity=1mL);
agit(sample=sample,mode=AgitationMode.ROTATION,duration=1min)
  with constraint(ConstraintRequirement.{requirement});
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert len(driver.actions) == 1
    assert driver.actions[0].gate['constraint']['requirements'] == [requirement.lower()]


def test_nested_scope_protocol_and_unconstrained_sibling():
    plan = plan_source('''
protocol Mix(sample) { agit(sample=sample,mode=shake,duration=1s); }
let sample=tube(label="S",load=[content(kind=formulation,type=buffer,code="B"):10uL]);
let target=tube(label="T",capacity=1mL);
with constraint(ConstraintRequirement.GENTLE) {
  target << [sample:1uL];
  with constraint(ConstraintRequirement.DARK_PROTECTED) { Mix(sample=sample); }
  Mix(sample=sample);
}
Mix(sample=sample);
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert [s.op for s in driver.actions] == ['Mutation', 'agit', 'agit', 'agit']
    assert [(s.gate or {}).get('constraint', {}).get('requirements', []) for s in driver.actions] == [
        ['gentle'], ['gentle', 'dark_protected'], ['gentle'], []]


@pytest.mark.parametrize('temperature,ok', [('4C', True), ('277.15K', True), ('37C', False), ('310.15K', False)])
def test_dynamic_thermal_conflict_before_driver(temperature, ok):
    plan = plan_source(f'''
protocol T(flag=true) {{
  let sample=tube(label="S",capacity=1mL);
  let temperature=4C;
  if flag {{ temperature={temperature}; }}
  with constraint(ConstraintRequirement.COLD_CHAIN) {{
    with env(thermal=temperature) {{ agit(sample=sample,mode=shake,duration=1s); }}
  }}
}}
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok == ok, result.diagnostics
    assert len(driver.actions) == int(ok)
    if not ok:
        assert 'RT_CONSTRAINT_ENV_CONFLICT' in [d.code for d in result.diagnostics]


def test_inapplicable_requirement_on_replayed_plan_is_rejected():
    plan = plan_source('let sample=tube(label="S"); agit(sample=sample,mode=shake,duration=1s);')
    step = next(s for p in plan.plans for s in p.steps if s.op == 'agit')
    step.gate['constraint'] = {'requirements': ['dropwise'], 'options': {}}
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert not driver.actions
    assert 'RT_CONSTRAINT_INVALID' in [d.code for d in result.diagnostics]


def test_driver_refusal_prevents_action():
    plan = plan_source('''let sample=tube(label="S");
agit(sample=sample,mode=shake,duration=1s) with constraint(ConstraintRequirement.GENTLE);''')
    driver = RecordingDriver(supported_requirements=set())
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert not driver.actions
    assert 'RT_DRIVER_REQUIREMENT_UNSUPPORTED' in [d.code for d in result.diagnostics]


def test_nested_customized_exclusivity_is_checked():
    _, semantic = compile_source('''
let schema=data_schema(label="S",fields=[target]);
let sample=tube(label="S");
with constraint(customized,schema_ref=schema) {
 with constraint(gentle) { sample << [sample:1uL]; }
}
''')
    assert 'SEM_CONSTRAINT_CUSTOMIZED_EXCLUSIVE' in [d.code for d in semantic.diagnostics]


@pytest.mark.parametrize('temperature', ['37C', '310.15K'])
def test_source_temperature_conflicts_have_owned_diagnostic(temperature):
    _, semantic = compile_source(f'''
let sample=tube(label="S");
with constraint(ConstraintRequirement.COLD_CHAIN) {{
 with env(thermal={temperature}) {{ agit(sample=sample,mode=shake,duration=1s); }}
}}
''')
    assert [d.code for d in semantic.diagnostics] == ['SEM_CONSTRAINT_ENV_CONFLICT']


@pytest.mark.parametrize('requirement', ['DROPWISE', 'SPREAD', 'PRESERVE_LAYERING', 'SEALED'])
def test_source_keeps_unaccepted_agitation_constraints_rejected(requirement):
    _, semantic = compile_source(f'''
let sample=tube(label="S");
agit(sample=sample,mode=shake,duration=1s) with constraint(ConstraintRequirement.{requirement});
''')
    assert [d.code for d in semantic.diagnostics] == ['SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH']


def test_runtime_conflict_does_not_move_material():
    plan = plan_source('''
protocol T(flag=true) {
 let source=tube(label="Source",load=[content(kind=formulation,type=buffer,code="B"):10uL]);
 let target=tube(label="Target",capacity=1mL);
 let temperature=4C;
 if flag { temperature=37C; }
 with env(thermal=temperature) {
  target << [source:5uL] with constraint(ConstraintRequirement.COLD_CHAIN);
 }
}
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert 'RT_CONSTRAINT_ENV_CONFLICT' in [d.code for d in result.diagnostics]
    assert not driver.actions
    containers = result.state.artifacts['material_state']['containers']
    volumes = {c['metadata']['label']: c['volume_uL'] for c in containers.values()}
    assert volumes == {'Source': 10, 'Target': 0}


def test_unresolved_explicit_temperature_in_plan_fails_before_action():
    plan = plan_source('''let sample=tube(label="S");
agit(sample=sample,mode=shake,duration=1s) with constraint(ConstraintRequirement.COLD_CHAIN);''')
    step = next(s for p in plan.plans for s in p.steps if s.op == 'agit')
    step.gate['env'] = {'thermal': {'kind': 'IRIdentifier', 'name': 'missing'}}
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert not driver.actions
    assert 'RT_CONSTRAINT_INVALID' in [d.code for d in result.diagnostics]


def test_unexecuted_branch_does_not_check_dynamic_constraint():
    plan = plan_source('''
protocol T(flag=false) {
 let sample=tube(label="S");
 let temperature=4C;
 if flag {
  temperature=37C;
  with env(thermal=temperature) {
   agit(sample=sample,mode=shake,duration=1s) with constraint(ConstraintRequirement.COLD_CHAIN);
  }
 }
 agit(sample=sample,mode=shake,duration=1s);
}
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert len(driver.actions) == 1
