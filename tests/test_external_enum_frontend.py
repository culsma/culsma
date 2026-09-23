"""External enum contracts through the source frontend, planning and execution."""
import json
import pytest
from culsma.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver

PREFIX = 'let x=tube(load=[content(kind=formulation,type=medium,code="M"):1mL]);'
CASES = [
    ('AgitationMode.VORTEX', '"vortex"', 'agit(sample=x,mode=VALUE,duration=1s);'),
    ('ReadoutQuantity.FLUORESCENCE', '"fluorescence"', 'let r=img(sample=x,quantity=VALUE);'),
    ('CentrifugeProgramOutput.PELLET', '"pellet"', 'let g=sep(sample=x,program=centrifuge_program(drive=300g,keep_source=VALUE));'),
    ('DisruptionMethod.SONICATION', '"sonication"', 'let g=sep(sample=x,program=disrupt_program(method=VALUE,duration=1s));'),
    ('DensityGradientAxis.DENSITY', '"density"', 'let g=frac(sample=x,program=density_gradient_program(axis=VALUE,order=top_to_bottom,bins=2));'),
    ('DensityGradientOrder.TOP_TO_BOTTOM', '"top_to_bottom"', 'let g=frac(sample=x,program=density_gradient_program(axis=density,order=VALUE,bins=2));'),
    ('PlateFormat.WELL_96', '"96well"', 'let p=plate(format=VALUE); p[A1] << [x:1uL];'),
    ('ScheduleMode.DISCRETE', '"discrete"', 'repeat tick in schedule(start=1,end=2,step=1,mode=VALUE) { agit(sample=x,mode=vortex,duration=1s); }'),
]


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


@pytest.mark.parametrize('new,old,statement', CASES)
@pytest.mark.parametrize('form', ['direct', 'alias', 'default'])
def test_new_and_legacy_forms_run_equivalently(new, old, statement, form):
    results = []
    for value in (new, old):
        params, declaration = '', ''
        if form == 'alias':
            declaration = f'let choice={value};'
            value = 'choice'
        elif form == 'default':
            params = f'(choice={value})'
            value = 'choice'
        source = f'protocol T{params} {{ {declaration}{PREFIX}{statement.replace("VALUE",value)} }}'
        compiled, semantic, typed = compile_source(source)
        assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
        assert typed.ok, [d.to_dict() for d in typed.diagnostics]
        plan = lower_ir_to_plan(compiled.ir)
        assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
        json.dumps(plan.to_dict())
        result = run(plan=plan,driver=StubDriver())
        assert result.ok, [d.to_dict() for d in result.diagnostics]
        json.dumps(result.user_result)
        results.append(result.state.artifacts.get('material_state'))
    if results:
        assert results[0] == results[1]


@pytest.mark.parametrize('value', ['ReadoutQuantity.FLUORESCENCE', '42', 'true'])
def test_wrong_family_or_shape_is_type_error(value):
    _, semantic, typed = compile_source(f'protocol T {{ {PREFIX} agit(sample=x,mode={value},duration=1s); }}')
    assert [d.code for d in typed.diagnostics].count('TYPE_EXTERNAL_ENUM_MISMATCH') == 1
    assert 'SEM_AGIT_MODE_UNKNOWN' not in [d.code for d in semantic.diagnostics]


def test_invalid_member_and_operation_subset_fail_semantically():
    for value in ('ReadoutQuantity.TYPO', 'ReadoutQuantity.PH'):
        _, semantic, _ = compile_source(f'protocol T {{ {PREFIX} let r=img(sample=x,quantity={value}); }}')
        assert 'SEM_INVALID_READOUT_QUANTITY' in [d.code for d in semantic.diagnostics]


def test_alias_captures_enum_before_later_assignment():
    source = f'''protocol T {{ {PREFIX}
      let original=ReadoutQuantity.FLUORESCENCE;
      let captured=original;
      original=ReadoutQuantity.PH;
      let r=img(sample=x,quantity=captured);
    }}'''
    compiled, semantic, typed = compile_source(source)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    assert run(plan=lower_ir_to_plan(compiled.ir),driver=StubDriver()).ok


def test_parameter_override_is_checked_after_binding():
    from culsma.domains.readout import ReadoutQuantity
    from culsma.domains.agitation import AgitationMode
    compiled, semantic, typed = compile_source(f'protocol T(q) {{ {PREFIX} let r=img(sample=x,quantity=q); }}')
    assert semantic.ok and typed.ok
    for value in (ReadoutQuantity.FLUORESCENCE, 'fluorescence'):
        plan=lower_ir_to_plan(compiled.ir, entry_args_by_protocol={'T': {'q': value}})
        assert not plan.diagnostics
        assert run(plan=plan,driver=StubDriver()).ok
    for value in (AgitationMode.VORTEX, ReadoutQuantity.PH, 2, 'TYPO'):
        plan=lower_ir_to_plan(compiled.ir, entry_args_by_protocol={'T': {'q': value}})
        assert not plan.plans
        assert 'PLAN_EXTERNAL_ENUM_INVALID' in [d.code for d in plan.diagnostics]


def test_runtime_enum_identity_and_json_plan_roundtrip():
    from culsma.domains.readout import ReadoutQuantity
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
    class InspectDriver(StubDriver):
        def execute(self, step):
            if step.op == 'img':
                assert step.args['quantity'] is ReadoutQuantity.FLUORESCENCE
            return super().execute(step)
    compiled, _, _ = compile_source(f'protocol T {{ {PREFIX} let r=img(sample=x,quantity="fluorescence"); }}')
    plan=lower_ir_to_plan(compiled.ir)
    payload=json.loads(json.dumps(plan.to_dict()))['plans'][0]
    reloaded=PlanProgram(plans=[ProtocolPlan(payload['protocol_id'],payload['protocol_name'],steps=[
        PlanStep(s['step_id'],s['op'],s['args'],s['deps'],s['gate']) for s in payload['steps']])])
    first=run(plan=plan,driver=InspectDriver())
    second=run(plan=reloaded,driver=InspectDriver())
    assert first.ok and second.ok
    assert first.state.artifacts['material_state'] == second.state.artifacts['material_state']


def test_runtime_rejects_foreign_enum_before_driver_execution():
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
    class NoExecuteDriver(StubDriver):
        def execute(self, step):
            raise AssertionError('invalid parameters must not reach driver')
    step=PlanStep('bad','img',{'quantity':{'kind':'ExternalEnum','enum':'AgitationMode','member':'VORTEX'}})
    result=run(plan=PlanProgram(plans=[ProtocolPlan('T','T',steps=[step])]),driver=NoExecuteDriver())
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


def test_runtime_branch_does_not_freeze_a_shadowed_legacy_token():
    source=f'''protocol T(flag=true) {{ {PREFIX}
      let vortex=AgitationMode.VORTEX;
      if flag {{ vortex=AgitationMode.SHAKE; }}
      agit(sample=x,mode=vortex,duration=1s);
    }}'''
    from culsma.domains.agitation import AgitationMode
    class InspectDriver(StubDriver):
        def execute(self, step):
            if step.op=='agit':
                assert step.args['mode'] is AgitationMode.SHAKE
            return super().execute(step)
    compiled,semantic,typed=compile_source(source)
    assert semantic.ok and typed.ok, [d.to_dict() for r in (semantic,typed) for d in r.diagnostics]
    assert run(plan=lower_ir_to_plan(compiled.ir),driver=InspectDriver()).ok


@pytest.mark.parametrize('initial,changed,statement', [
    ('ReadoutQuantity.FLUORESCENCE','ReadoutQuantity.CUSTOMIZED','let r=img(sample=x,quantity=q);'),
    ('AgitationMode.VORTEX','AgitationMode.INVERT','agit(sample=x,mode=q,duration=1s);'),
])
def test_dynamic_enum_rechecks_dependent_contract_before_execution(initial, changed, statement):
    source=f'protocol T(flag=true) {{ {PREFIX} let q={initial}; if flag {{ q={changed}; }} {statement} }}'
    compiled,semantic,typed=compile_source(source)
    assert semantic.ok and typed.ok
    plan=lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    result=run(plan=plan,driver=StubDriver())
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]
