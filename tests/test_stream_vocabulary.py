import json
import pytest
from culsma.domains.stream import ObservationUnitBase, ObservationUnit, OBSERVATION_UNITS, STANDARD_OBSERVATION_UNITS
from culsma.domains.readout import ReadoutQuantity
from culsma.pipeline.external_boundary import ExternalEnumCodec
from culsma.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver


class LabUnit(ObservationUnitBase):
    DROPLET = 'lab_droplet'


def registry():
    return STANDARD_OBSERVATION_UNITS.with_type(LabUnit, 'example.observation.unit')


def compile_source(unit, *, params='', prefix=''):
    source=f'''protocol T{params} {{
      let cells=tube();
      {prefix}
      let events=stream(sample=cells,unit={unit});
    }}'''
    compiled=compile_ast(resolve_program(parse(source)).prepared_program)
    semantic=validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed=typecheck(compiled.ir,analysis=compiled.analysis)
    return compiled, semantic, typed


def execute(unit, **kwargs):
    compiled, semantic, typed=compile_source(unit,**kwargs)
    assert semantic.ok, semantic.diagnostics
    assert typed.ok, typed.diagnostics
    plan=lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics, plan.diagnostics
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, result.diagnostics
    return result


@pytest.mark.parametrize('unit', ['ObservationUnit.SINGLE_CELL','single_cell','"single_cell"'])
def test_standard_source_keeps_result_shape(unit):
    result=execute(unit)
    events=result.state.artifacts['local_bindings']['events']
    assert events['unit_kind'] == 'single_cell'
    assert 'unit_type' not in events


@pytest.mark.parametrize('unit', ['old_custom_unit', '"old_custom_unit"'])
def test_historical_units_remain_metadata(unit):
    assert execute(unit).state.artifacts['local_bindings']['events']['unit_kind']=='old_custom_unit'


@pytest.mark.parametrize('form',['direct','alias','default','branch'])
def test_extension_identity_through_source_forms(form):
    with registry().activate():
        unit,params,prefix='LabUnit.DROPLET','',''
        if form=='alias':
            prefix='let u=LabUnit.DROPLET;'
            unit='u'
        if form=='default':
            params='(u=LabUnit.DROPLET)'
            unit='u'
        if form=='branch':
            params='(flag=true)'
            prefix='let u=ObservationUnit.SINGLE_CELL; if flag { u=LabUnit.DROPLET; }'
            unit='u'
        result=execute(unit,params=params,prefix=prefix)
        events=result.state.artifacts['local_bindings']['events']
        assert events['unit_kind']=='lab_droplet'
        assert events['unit_type']==registry().encode(LabUnit.DROPLET)
        json.dumps(result.user_result)


@pytest.mark.parametrize('unit,code', [
    ('ReadoutQuantity.PH','TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('42','TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('ObservationUnit.TYPO','SEM_INVALID_EXTERNAL_PARAMETER'),
    ('NotInstalled.VALUE','SEM_INVALID_EXTERNAL_PARAMETER'),
])
def test_invalid_source_types(unit,code):
    _,semantic,typed=compile_source(unit)
    assert code in [d.code for d in semantic.diagnostics+typed.diagnostics]


def test_entry_override_and_json_roundtrip():
    with registry().activate():
        compiled,_,_=compile_source('u',params='(u=ObservationUnit.SINGLE_CELL)')
        plan=lower_ir_to_plan(compiled.ir,entry_args_by_protocol={'T':{'u':LabUnit.DROPLET}})
        assert not plan.diagnostics
        payload=json.loads(json.dumps(plan.to_dict()))['plans'][0]
        loaded=PlanProgram(plans=[ProtocolPlan(payload['protocol_id'],payload['protocol_name'],steps=[
            PlanStep(s['step_id'],s['op'],s['args'],s['deps'],s['gate']) for s in payload['steps']])])
        result=run(plan=loaded,driver=StubDriver())
        assert result.ok, result.diagnostics
        assert result.state.artifacts['local_bindings']['events']['unit_type']['id']=='example.observation.unit'
        rejected=lower_ir_to_plan(compiled.ir,entry_args_by_protocol={'T':{'u':ReadoutQuantity.PH}})
        assert not rejected.plans
    result=run(plan=loaded,driver=StubDriver())
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


def test_registry_rejects_wrong_domain_and_wire_collisions_and_restores_context():
    with pytest.raises(TypeError):
        registry().with_type(ReadoutQuantity,'wrong.domain')
    class Collision(ObservationUnitBase):
        CELL='single_cell'
    with pytest.raises(ValueError):
        registry().with_type(Collision,'collision')
    with pytest.raises(ValueError):
        registry().with_type(LabUnit,'duplicate')
    with registry().activate():
        codec=ExternalEnumCodec()
        payload=codec.encode(LabUnit.DROPLET)
        assert codec.decode(payload) is LabUnit.DROPLET
        payload['version']=2
        with pytest.raises(ValueError):
            codec.decode(payload)
    assert 'LabUnit' not in OBSERVATION_UNITS.current.types


def test_cross_domain_namespace_collision_is_rejected_in_either_order():
    from culsma.domains.fractionation import ChromatographyAxisBase, STANDARD_CHROMATOGRAPHY_REGISTRY
    ConflictingAxis=ChromatographyAxisBase('LabUnit',{'TIME':'lab_time'})
    chromatography=STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(ConflictingAxis,'example.axis')
    with registry().activate():
        with pytest.raises(ValueError,match='namespace collision'):
            with chromatography.activate():
                pass
    with chromatography.activate():
        with pytest.raises(ValueError,match='namespace collision'):
            with registry().activate():
                pass


def test_seeded_units_keep_data_and_explicit_unit_overrides():
    from copy import deepcopy
    from culsma.runtime.stream_values import StreamValueBuilder
    from culsma.runtime.state import RuntimeState
    state=RuntimeState()
    seed=[{'kind':'unit_ref','id':'cell-a','unit_kind':'single_cell','signals':{'x':3}}, {'id':'drop-a','signals':{'x':7}}]
    original=deepcopy(seed)
    state.artifacts['stream_units']={'events':seed}
    with registry().activate():
        stream=StreamValueBuilder.build({'unit':LabUnit.DROPLET,'sample':'cells'},state,target_name='events')
        assert stream['items'][0]['unit_kind']=='single_cell'
        assert 'unit_type' not in stream['items'][0]
        assert stream['items'][1]['unit_type']==registry().encode(LabUnit.DROPLET)
        assert stream['items'][1]['signals']=={'x':7}
    assert seed==original
