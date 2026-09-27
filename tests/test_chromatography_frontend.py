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
from culsma.domains.fractionation import ChromatographyAxis, ChromatographyOrder
from test_chromatography_extensions import installed_registry, LabAxis, LabOrder

PREFIX = 'let x=tube(load=[content(kind=formulation,type=medium,code="M"):1mL]);'


def compile_source(axis, order, *, params='', declaration=''):
    source = f'''protocol T{params} {{ {PREFIX} {declaration}
        let g=frac(sample=x,program=chromatography_program(axis={axis},order={order},bins=2));
    }}'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


class ExtensionDriver(StubDriver):
    supported_chromatography_types = frozenset({
        ('example.chromatography.axis', 1), ('example.chromatography.order', 1),
    })

    def execute(self, step):
        if step.op == 'frac':
            args = {a['name']: a['value'] for a in step.args['program']['args']}
            assert args['axis'] is LabAxis.ELUTION_VOLUME
            assert args['order'] is LabOrder.SMALL_TO_LARGE
        return super().execute(step)


@pytest.mark.parametrize('axis,order', [
    ('ChromatographyAxis.RETENTION_TIME', 'ChromatographyOrder.EARLY_TO_LATE'),
    ('retention_time', 'early_to_late'), ('"retention_time"', '"early_to_late"'),
    ('"historical_axis"', '"historical_order"'),
])
def test_standard_and_historical_source_remain_executable(axis, order):
    compiled, semantic, typed = compile_source(axis, order)
    assert semantic.ok, semantic.diagnostics
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, result.diagnostics


@pytest.mark.parametrize('form', ['direct', 'alias', 'default', 'override'])
def test_python_extensions_through_source_and_runtime(form):
    with installed_registry().activate():
        axis, order = 'LabAxis.ELUTION_VOLUME', 'LabOrder.SMALL_TO_LARGE'
        params, declaration, arguments = '', '', {}
        if form == 'alias':
            declaration=f'let a={axis}; let o={order};'
            axis, order='a', 'o'
        if form == 'default':
            params=f'(a={axis},o={order})'
            axis, order='a', 'o'
        if form == 'override':
            params='(a=ChromatographyAxis.RETENTION_TIME,o=ChromatographyOrder.EARLY_TO_LATE)'
            axis, order='a','o'
            arguments={'a':LabAxis.ELUTION_VOLUME, 'o':LabOrder.SMALL_TO_LARGE}
        compiled, semantic, typed = compile_source(axis, order, params=params, declaration=declaration)
        assert semantic.ok, semantic.diagnostics
        assert typed.ok, typed.diagnostics
        plan = lower_ir_to_plan(compiled.ir, entry_args_by_protocol={'T':arguments})
        assert not plan.diagnostics, plan.diagnostics
        json.dumps(plan.to_dict())
        result = run(plan=plan, driver=ExtensionDriver())
        assert result.ok, result.diagnostics


def test_driver_cannot_gain_extension_support_from_registration():
    with installed_registry().activate():
        compiled, _, _ = compile_source('LabAxis.ELUTION_VOLUME','LabOrder.SMALL_TO_LARGE')
        plan = lower_ir_to_plan(compiled.ir)
        class RejectExecution(StubDriver):
            def execute(self, step):
                assert step.op != 'frac'
                return super().execute(step)
        result=run(plan=plan,driver=RejectExecution())
        assert not result.ok
        assert 'RT_DRIVER_REQUIREMENT_UNSUPPORTED' in [d.code for d in result.diagnostics]


@pytest.mark.parametrize('axis,order,code', [
    ('LabOrder.SMALL_TO_LARGE', 'LabOrder.SMALL_TO_LARGE', 'TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('LabAxis.TYPO', 'LabOrder.SMALL_TO_LARGE', 'SEM_INVALID_PROGRAM_ARG_VALUE'),
    ('LabAxis.ELUTION_VOLUME', 'ChromatographyOrder.EARLY_TO_LATE', 'SEM_INVALID_PROGRAM_ARG_VALUE'),
    ('"elution_volume"', 'LabOrder.SMALL_TO_LARGE', 'SEM_INVALID_PROGRAM_ARG_VALUE'),
])
def test_extension_errors_have_earliest_stage_owner(axis, order, code):
    with installed_registry().activate():
        _, semantic, typed=compile_source(axis, order)
        assert code in [d.code for d in semantic.diagnostics+typed.diagnostics]


def test_bound_override_rechecks_pair_and_rejects_wrong_domain():
    from culsma.domains.readout import ReadoutQuantity
    with installed_registry().activate():
        compiled, semantic, typed = compile_source('a', 'o',
            params='(a=ChromatographyAxis.RETENTION_TIME,o=ChromatographyOrder.EARLY_TO_LATE)')
        assert semantic.ok and typed.ok
        for arguments in ({'a': LabAxis.ELUTION_VOLUME}, {'a': ReadoutQuantity.PH}):
            plan = lower_ir_to_plan(compiled.ir, entry_args_by_protocol={'T':arguments})
            assert not plan.plans
            assert 'PLAN_EXTERNAL_ENUM_INVALID' in [d.code for d in plan.diagnostics]


def test_plan_json_roundtrip_and_uninstalled_extension_rejection():
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
    with installed_registry().activate():
        compiled, _, _ = compile_source('LabAxis.ELUTION_VOLUME','LabOrder.SMALL_TO_LARGE')
        plan = lower_ir_to_plan(compiled.ir)
        payload=json.loads(json.dumps(plan.to_dict()))['plans'][0]
        reloaded=PlanProgram(plans=[ProtocolPlan(payload['protocol_id'],payload['protocol_name'],steps=[
            PlanStep(s['step_id'],s['op'],s['args'],s['deps'],s['gate']) for s in payload['steps']])])
        first=run(plan=plan,driver=ExtensionDriver())
        second=run(plan=reloaded,driver=ExtensionDriver())
        assert first.ok and second.ok
        assert first.state.artifacts['material_state'] == second.state.artifacts['material_state']
    result=run(plan=reloaded,driver=ExtensionDriver())
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


def test_source_namespace_shadowing_uses_record_value_and_checks_wrong_shape():
    with installed_registry().activate():
        compiled, semantic, typed=compile_source('LabAxis.ELUTION_VOLUME','ChromatographyOrder.EARLY_TO_LATE',
            declaration='let LabAxis={ELUTION_VOLUME: ChromatographyAxis.RETENTION_TIME};')
        assert semantic.ok and typed.ok
        assert run(plan=lower_ir_to_plan(compiled.ir),driver=StubDriver()).ok
        _, semantic, typed=compile_source('LabAxis.ELUTION_VOLUME','ChromatographyOrder.EARLY_TO_LATE',
            declaration='let LabAxis=42;')
        assert not semantic.ok or not typed.ok


def test_old_text_and_explicit_standard_have_same_material_result():
    results=[]
    for axis, order in [('retention_time','early_to_late'),
                        ('ChromatographyAxis.RETENTION_TIME','ChromatographyOrder.EARLY_TO_LATE')]:
        compiled, semantic, typed=compile_source(axis,order)
        assert semantic.ok and typed.ok
        result=run(plan=lower_ir_to_plan(compiled.ir),driver=StubDriver())
        assert result.ok
        results.append(result.state.artifacts['material_state'])
    assert results[0] == results[1]


def test_runtime_branch_preserves_extension_identity_and_pair_checks():
    with installed_registry().activate():
        source=f'''protocol T(flag=true) {{
            {PREFIX}
            let a=ChromatographyAxis.RETENTION_TIME;
            let o=ChromatographyOrder.EARLY_TO_LATE;
            if flag {{ a=LabAxis.ELUTION_VOLUME; o=LabOrder.SMALL_TO_LARGE; }}
            let g=frac(sample=x,program=chromatography_program(axis=a,order=o,bins=2));
        }}'''
        compiled=compile_ast(resolve_program(parse(source)).prepared_program)
        semantic=validate(compiled.ir,analysis=compiled.analysis,enforce_binding=True)
        typed=typecheck(compiled.ir,analysis=compiled.analysis)
        assert semantic.ok, semantic.diagnostics
        assert typed.ok, typed.diagnostics
        plan=lower_ir_to_plan(compiled.ir)
        assert not plan.diagnostics
        result=run(plan=plan,driver=ExtensionDriver())
        assert result.ok, result.diagnostics
        json.dumps(result.user_result)


def test_unknown_members_and_unregistered_names_cannot_execute():
    compiled, semantic, typed=compile_source('LabAxis.ELUTION_VOLUME','LabOrder.SMALL_TO_LARGE')
    assert not semantic.ok or not typed.ok
    with installed_registry().activate():
        compiled, _, _=compile_source('LabAxis.TYPO','LabOrder.SMALL_TO_LARGE')
        assert not lower_ir_to_plan(compiled.ir).plans


def test_dynamic_pair_mismatch_is_rejected_before_frac_executes():
    with installed_registry().activate():
        source=f'''protocol T(flag=true) {{
            {PREFIX}
            let a=ChromatographyAxis.RETENTION_TIME;
            if flag {{ a=LabAxis.ELUTION_VOLUME; }}
            let g=frac(sample=x,program=chromatography_program(
                axis=a,order=ChromatographyOrder.EARLY_TO_LATE,bins=2));
        }}'''
        compiled=compile_ast(resolve_program(parse(source)).prepared_program)
        assert typecheck(compiled.ir,analysis=compiled.analysis).ok
        plan=lower_ir_to_plan(compiled.ir)
        assert not plan.diagnostics
        class NoFrac(ExtensionDriver):
            def execute(self, step):
                assert step.op != 'frac'
                return super().execute(step)
        result=run(plan=plan,driver=NoFrac())
        assert not result.ok
        assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


def test_alias_keeps_captured_extension_after_reassignment():
    with installed_registry().activate():
        compiled, semantic, typed=compile_source('captured','LabOrder.SMALL_TO_LARGE',
            declaration='let a=LabAxis.ELUTION_VOLUME; let captured=a; a=ChromatographyAxis.RETENTION_TIME;')
        assert semantic.ok and typed.ok
        result=run(plan=lower_ir_to_plan(compiled.ir),driver=ExtensionDriver())
        assert result.ok, result.diagnostics
