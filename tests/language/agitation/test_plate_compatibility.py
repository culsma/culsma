"""Released source/payloads, old plans, and explicit carrier membership boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from culsma.common.source import Span
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram,ProtocolPlan,PlanStep
from culsma.runtime.executor import run
from culsma.runtime.state import init_state

FIXTURE=Path(__file__).resolve().parents[2]/'fixtures/plate_compatibility_v1.json'
CASES=json.loads(FIXTURE.read_text())['cases']


class CompatibilityDriver(StubDriver):
    def __init__(self):super().__init__();self.actions=[]
    def execute(self,step):
        self.actions.append({'op':step.op,'args':step.args,'gate':step.gate})
        return super().execute(step)


class PlateCompatibilityFixture:
    def compile(self,source):
        compiled=compile_ast(resolve_program(parse(source)).prepared_program)
        checked=validate(compiled.ir,analysis=compiled.analysis)
        typed=typecheck(compiled.ir,analysis=compiled.analysis)
        assert typed.ok,typed.diagnostics
        plan=lower_ir_to_plan(checked.ir,analysis=compiled.analysis)
        return checked,plan

    def restore(self,raw):
        def span(value):
            return Span(**{key:value[key] for key in ('line','col','start','end')}) if value else None
        plans=[]
        for item in raw['plans']:
            steps=[PlanStep(s['step_id'],s['op'],s['args'],s.get('deps',[]),s.get('gate'),span(s.get('span'))) for s in item['steps']]
            values={key:item[key] for key in ('protocol_id','protocol_name','entry_kind','output_name','returns','return_value','return_bindings') if key in item}
            plans.append(ProtocolPlan(**values,steps=steps,span=span(item.get('span'))))
        return PlanProgram(plans=plans,span=span(raw.get('span')))

    def published_actions(self,actions):
        result=deepcopy(actions)
        for action in result:
            if action['op']=='AllocContainer':
                for key in ('carrier_rows','carrier_cols','plate_ref'):action['args'].pop(key,None)
        return json.loads(json.dumps(result))


class TestPlateCompatibility:
    @pytest.mark.parametrize('case',CASES,ids=lambda c:c['name'])
    def test_old_source_acceptance(self,case):
        checked,plan=PlateCompatibilityFixture().compile(case['source'])
        assert checked.ok and not plan.diagnostics,(checked.diagnostics,plan.diagnostics)
        driver=CompatibilityDriver();result=run(plan,driver)
        assert result.ok,result.diagnostics
        assert PlateCompatibilityFixture().published_actions(driver.actions)==PlateCompatibilityFixture().published_actions(case['actions'])
        old=case['state']['artifacts'].get('material_state',{}).get('containers',{})
        current=result.state.artifacts.get('material_state',{}).get('containers',{})
        assert {k:c.get('volume_uL') for k,c in current.items()}=={k:c.get('volume_uL') for k,c in old.items()}

    @pytest.mark.parametrize('name',['label_only_environment','whole_plate_readout'])
    def test_legacy_payloads(self,name):
        case=next(c for c in CASES if c['name']==name)
        _,plan=PlateCompatibilityFixture().compile(case['source']);driver=CompatibilityDriver()
        result=run(plan,driver);assert result.ok
        assert json.loads(json.dumps(driver.actions))==case['actions']
        assert result.state.artifacts['data_objects']==case['state']['artifacts']['data_objects']

    @pytest.mark.parametrize('mode',['tap','method'])
    def test_inline_target_rejects(self,mode):
        source=('agit(sample=plate(format="96well"),mode=tap);' if mode=='tap' else
            'protocol T(flag=true) {let method="shake"; if flag {method="tap";} agit(sample=plate(format="96well"),mode=method);}')
        checked,plan=PlateCompatibilityFixture().compile(source)
        if mode == 'tap':
            assert not checked.ok and 'SEM_AGIT_ARG_CONFLICT' in [d.code for d in checked.diagnostics]
        else:
            assert checked.ok and not plan.diagnostics
            driver=CompatibilityDriver();result=run(plan,driver)
            assert not result.ok and not driver.actions
            assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]
        direct=PlanProgram(plans=[ProtocolPlan('entry','T',steps=[PlanStep('action','agit',{
            'sample':{'kind':'IRCall','name':'plate','args':[]},'mode':'tap'})])])
        driver=CompatibilityDriver();result=run(direct,driver)
        assert not result.ok and not driver.actions

    @pytest.mark.parametrize('case',CASES,ids=lambda c:c['name'])
    def test_old_plan_replay(self,case):
        driver=CompatibilityDriver();result=run(PlateCompatibilityFixture().restore(case['plan']),driver)
        assert result.ok,result.diagnostics
        assert json.loads(json.dumps(driver.actions))==case['actions']

    @pytest.mark.parametrize('skip_old_steps',[True,False])
    @pytest.mark.parametrize('null_membership',[True,False])
    def test_legacy_membership_cannot_silently_skip(self,skip_old_steps,null_membership):
        case=next(c for c in CASES if c['name']=='selected_well_partition')
        source=case['source'] if skip_old_steps else ';'.join(case['source'].split(';')[:2])+';'
        checked,plan=PlateCompatibilityFixture().compile(source+' agit(sample=p,mode=tap);')
        assert checked.ok and not plan.diagnostics
        state=init_state(plan);state.artifacts.update(deepcopy(case['state']['artifacts']))
        if null_membership:
            for container in state.artifacts['material_state']['containers'].values():
                if container.get('metadata',{}).get('kind')=='well':container['metadata']['plate_ref']=None
        if skip_old_steps:state.step_status.update(deepcopy(case['state']['step_status']))
        driver=CompatibilityDriver();result=run(plan,driver,state)
        assert not result.ok
        assert 'MAT_PLATE_REF_INVALID' in [d.code for d in result.diagnostics]
        assert not any(a['op']=='agit' for a in driver.actions)
        assert all(c.get('metadata',{}).get('plate_ref') is None for c in result.state.artifacts['material_state']['containers'].values() if c.get('metadata',{}).get('kind')=='well')

    def test_opaque_plate_identity_and_runtime_label(self):
        source='protocol T(flag=true) { let label="A"; if flag {label="B";} let p=plate(label=label); agit(sample=p,mode=tap); } T();'
        checked,plan=PlateCompatibilityFixture().compile(source);assert checked.ok and not plan.diagnostics
        driver=CompatibilityDriver();result=run(plan,driver);assert result.ok,result.diagnostics
        action=next(a for a in driver.actions if a['op']=='agit')
        assert action['args']['sample']['label']=='B'
        assert action['args']['sample']['rows'] is None and action['args']['sample']['cols'] is None
