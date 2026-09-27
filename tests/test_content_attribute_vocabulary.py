"""Source-to-runtime checks for open typed content metadata."""
import json
import pytest
from culsma.domains.content import CONTENT_ROLES, ContentRoleBase, ContentRole
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run

class LabRole(ContentRoleBase):
    SUPPORT = 'lab_support'


def compile_source(attrs, prefix='', params=''):
    source=f'''protocol T{params} {{ {prefix}
      let x=tube(load=[content(kind=formulation,type=medium,code="M",attrs={{{attrs}}}):1mL]);
    }}'''
    compiled=compile_ast(resolve_program(parse(source)).prepared_program)
    semantic=validate(compiled.ir,analysis=compiled.analysis,enforce_binding=True)
    typed=typecheck(compiled.ir,analysis=compiled.analysis)
    return compiled, semantic, typed


def execute(attrs, **kwargs):
    compiled,semantic,typed=compile_source(attrs,**kwargs)
    assert semantic.ok, semantic.diagnostics
    assert typed.ok, typed.diagnostics
    plan=lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics, plan.diagnostics
    json.dumps(plan.to_dict())
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, result.diagnostics
    return result.state.artifacts['material_state']['content_registry']['M']['content_attrs']


@pytest.mark.parametrize('role',list(ContentRole))
def test_standard_roles_preserve_existing_spellings(role):
    assert execute(f'role:ContentRole.{role.name}') == {'role':role.value}


@pytest.mark.parametrize('form',['culture','"culture"','ContentRole.CULTURE'])
def test_standard_and_legacy_forms_agree(form):
    assert execute(f'role:{form},state:ContentState.STOCK,bead_property:BeadProperty.MAGNETIC') == {
        'role':'culture','state':'stock','bead_property':'magnetic'}


def test_open_metadata_remains_open():
    assert execute('role:old_role,state:true,extra:"unchanged"') == {
        'role':'old_role','state':True,'extra':'unchanged'}


@pytest.mark.parametrize('form',['direct','alias','default'])
def test_extension_keeps_stable_identity(form):
    registry=CONTENT_ROLES.standard_registry.with_type(LabRole,'example.content.role')
    with registry.activate():
        role,prefix,params='LabRole.SUPPORT','',''
        if form=='alias':
            role,prefix='r','let r=LabRole.SUPPORT;'
        if form=='default':
            role,params='r','(r=LabRole.SUPPORT)'
        assert execute(f'role:{role}',prefix=prefix,params=params)=={'role':registry.encode(LabRole.SUPPORT)}


@pytest.mark.parametrize('role,code',[
    ('ContentState.STOCK','TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('ContentRole.TYPO','SEM_INVALID_EXTERNAL_PARAMETER'),
    ('MissingRole.VALUE','SEM_INVALID_EXTERNAL_PARAMETER'),
])
def test_bad_typed_metadata_fails_at_frontend(role,code):
    _,semantic,typed=compile_source(f'role:{role}')
    assert code in [d.code for d in semantic.diagnostics+typed.diagnostics]


def test_entry_override_and_reloaded_plan_validate_identity():
    from culsma.domains.content import ContentState
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
    compiled,semantic,typed=compile_source('role:r',params='(r=ContentRole.CULTURE)')
    assert semantic.ok and typed.ok
    wrong=lower_ir_to_plan(compiled.ir,entry_args_by_protocol={'T':{'r':ContentState.STOCK}})
    assert not wrong.plans
    assert 'PLAN_EXTERNAL_ENUM_INVALID' in [d.code for d in wrong.diagnostics]
    registry=CONTENT_ROLES.standard_registry.with_type(LabRole,'example.content.role')
    with registry.activate():
        plan=lower_ir_to_plan(compiled.ir,entry_args_by_protocol={'T':{'r':LabRole.SUPPORT}})
        assert not plan.diagnostics
        payload=json.loads(json.dumps(plan.to_dict()))['plans'][0]
        loaded=PlanProgram(plans=[ProtocolPlan(payload['protocol_id'],payload['protocol_name'],steps=[
            PlanStep(s['step_id'],s['op'],s['args'],s['deps'],s['gate']) for s in payload['steps']])])
        result=run(plan=loaded,driver=StubDriver())
        assert result.ok, result.diagnostics
        assert result.state.artifacts['material_state']['content_registry']['M']['content_attrs']['role']==registry.encode(LabRole.SUPPORT)
    result=run(plan=loaded,driver=StubDriver())
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


def test_conditional_binding_keeps_metadata_type():
    registry=CONTENT_ROLES.standard_registry.with_type(LabRole,'example.content.role')
    with registry.activate():
        assert execute('role:r',params='(flag=true)',prefix='let r=ContentRole.CULTURE; if flag { r=LabRole.SUPPORT; }')['role']==registry.encode(LabRole.SUPPORT)


def test_shadowed_namespace_is_a_record_value():
    assert execute('role:ContentRole.CULTURE',prefix='let ContentRole={CULTURE:"old_role"};')['role']=='old_role'


def test_case_variant_extension_stays_opaque_metadata():
    class LabCarrier(ContentRoleBase):
        CARRIER='CARRIER'
    registry=CONTENT_ROLES.standard_registry.with_type(LabCarrier,'example.carrier')
    with registry.activate():
        assert execute('role:LabCarrier.CARRIER')['role']==registry.encode(LabCarrier.CARRIER)
