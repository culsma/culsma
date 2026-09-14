"""Dropwise delivery survives source lowering without changing material amounts."""

import pytest

from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


def compile_source(body):
    source = """protocol T {
        let source = tube(label = "Source", capacity = 1mL, load = [
            content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER,
                    code = "BUFFER"):200uL
        ]);
        let target = tube(label = "Target", capacity = 1mL);
    """ + body + "\n}"
    return compile_ast(resolve_program(parse(source)).prepared_program)


def build_plan(body):
    compiled = compile_source(body)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    return plan


def transfer_payloads(result):
    return [event.payload['driver_payload'] for event in result.events
            if event.kind == 'STEP_COMPLETED'
            and event.payload.get('driver_payload', {}).get('op') == 'Mutation']


def container_by_label(result, label):
    return next(container for container in
                result.state.artifacts['material_state']['containers'].values()
                if container.get('metadata', {}).get('label') == label)


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
@pytest.mark.parametrize('form', ['trailing', 'block'])
@pytest.mark.parametrize('selection,moved', [('source:150uL', 150), ('source', 200)])
def test_dropwise_is_delivered_to_driver_and_preserves_transfer_amount(driver_type, form, selection, moved):
    transfer = f'target << [{selection}]'
    body = (transfer + ' with constraint(dropwise);' if form == 'trailing'
            else 'with constraint(dropwise) { ' + transfer + '; }')
    plan = build_plan(body)
    mutation = next(step for protocol in plan.plans for step in protocol.steps if step.op == 'Mutation')
    assert mutation.gate['constraint']['requirements'] == ['dropwise']
    assert not mutation.gate['constraint'].get('options')
    result = run(plan=plan, driver=driver_type(supported_requirements={'dropwise'}))
    assert result.ok, result.diagnostics
    assert container_by_label(result, 'Source')['volume_uL'] == 200 - moved
    assert container_by_label(result, 'Target')['volume_uL'] == moved
    assert container_by_label(result, 'Target')['components']['BUFFER'] == moved
    payload, = transfer_payloads(result)
    if driver_type is HumanDriver:
        assert any('drop by drop' in line for line in payload['instruction']['details'])
    else:
        assert payload['binding']['requirement_flags'] == ['dropwise']
        assert payload['binding']['action'] == 'material.transfer'


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
def test_driver_without_dropwise_support_fails_before_moving_material(driver_type):
    plan = build_plan('target << [source:150uL] with constraint(dropwise);')
    result = run(plan=plan, driver=driver_type(supported_requirements={'gentle'}))
    assert not result.ok
    assert 'RT_DRIVER_REQUIREMENT_UNSUPPORTED' in [d.code for d in result.diagnostics]
    assert container_by_label(result, 'Source')['volume_uL'] == 200
    assert container_by_label(result, 'Target')['volume_uL'] == 0
    assert transfer_payloads(result) == []


def test_dropwise_combines_with_gentle_and_does_not_leak_outside_scope():
    plan = build_plan('''
        with constraint(gentle) {
            target << [source:50uL] with constraint(dropwise);
            target << [source:50uL];
        }
        target << [source:50uL];
    ''')
    result = run(plan=plan, driver=HumanDriver(supported_requirements={'gentle', 'dropwise'}))
    assert result.ok, result.diagnostics
    payloads = transfer_payloads(result)
    notes = [p['instruction']['details'] for p in payloads]
    assert any('drop by drop' in line for line in notes[0])
    assert any('Handle gently' in line for line in notes[0])
    assert not any('drop by drop' in line for line in notes[1])
    assert any('Handle gently' in line for line in notes[1])
    assert not any('drop by drop' in line or 'Handle gently' in line for line in notes[2])
    assert container_by_label(result, 'Target')['volume_uL'] == 150


@pytest.mark.parametrize('operation', [
    'agit(sample = source, mode = shake, duration = 1s);',
    'sep(sample = source, program = centrifuge_program(drive = 12000g));',
])
def test_dropwise_rejects_unrelated_operation_families(operation):
    compiled = compile_source('with constraint(dropwise) { ' + operation + ' }')
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert not result.ok
    assert 'SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH' in [d.code for d in result.diagnostics]


def test_dropwise_does_not_accept_uncontracted_drop_parameters():
    compiled = compile_source('target << [source:150uL] with constraint(dropwise, drop_count = 10);')
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert not result.ok
    assert 'SEM_CONSTRAINT_UNKNOWN_OPTION' in [d.code for d in result.diagnostics]
