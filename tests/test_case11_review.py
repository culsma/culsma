"""Section 2.2 continuation gates, material identity and physical output."""
from pathlib import Path

import pytest

import importlib.util
_metrics_spec = importlib.util.spec_from_file_location("legacy_benchmark_metrics",
    Path(__file__).resolve().parents[1] / "archive/benchmarks-legacy/tools/benchmark_metrics.py")
_metrics = importlib.util.module_from_spec(_metrics_spec)
_metrics_spec.loader.exec_module(_metrics)
final_material_records = _metrics.final_material_records
from culsma.cli import _to_jsonable
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run

CASE = Path(__file__).resolve().parents[1] / 'archive/benchmarks-legacy/cases/11/protocol.culs'


def execute(driver=None, proceed_immediately=True, **inputs):
    args = ', '.join(f'{k} = {str(v).lower()}' for k, v in inputs.items())
    source = CASE.read_text().replace('proceed_immediately = true\n);',
        f'proceed_immediately = {str(proceed_immediately).lower()}' + (', ' + args if args else '') + '\n);')
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    validated = validate(compiled.ir, analysis=compiled.analysis)
    assert validated.ok, validated.diagnostics
    typed = typecheck(validated.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    result = run(plan=plan, driver=driver or HumanDriver())
    assert result.ok and not result.diagnostics, result.diagnostics
    return result


def events(result):
    return [e for e in result.events if e.kind == 'STEP_COMPLETED']


def workflow_status(result):
    return next(d['result'] for d in result.state.artifacts['data_objects'].values()
                if 'processing_stage' in d['result'])


def discards(result):
    lines = CASE.read_text().splitlines()
    return [e for e in events(result) if 'waste <<' in lines[e.span.line - 1]]


def spins(result):
    return [e for e in events(result)
            if e.payload.get('material_delta', {}).get('program_kind') == 'centrifuge_program']


def entry(container, code):
    return next(e for e in container['component_entries'] if e['content_ref'] == code and e['amount'] > 0)


def assert_stopped(result):
    status = workflow_status(result)
    assert status['can_continue'] is False
    assert status['needs_attention'] is True
    assert status['ready_for_amplification'] is False
    assert status['storage_complete'] is False


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
@pytest.mark.parametrize('immediate', [True, False])
def test_success_preserves_dna_binding_and_counts_returned_physical_tube(driver_type, immediate):
    result = execute(driver_type(), proceed_immediately=immediate)
    status = workflow_status(result)
    assert status['template_switch_program_completed'] is True
    assert status['can_continue'] is True and status['needs_attention'] is False
    assert status['ready_for_amplification'] is immediate
    assert status['storage_complete'] is (not immediate)
    assert status['input_material_code'] == 'CAPTURED_CDNA'
    assert len(discards(result)) == (2 if immediate else 3)
    assert len(spins(result)) == 4
    returned = result.state.artifacts['protocol_outputs']['entry']['value']
    material = result.state.artifacts['material_state']['containers'][returned['id']]
    assert returned['label'] == 'BeadBoundCapturedCDNAInput'
    assert material['metadata']['capacity_uL'] == 200
    assert returned['volume_uL'] == pytest.approx(100.4001 if immediate else 125.4001)
    assert entry(material, 'CAPTURED_CDNA')['relation'] == 'bead_bound'
    assert entry(material, 'CAPTURED_CDNA')['quantity']['value'] == pytest.approx(0.0001)
    assert entry(material, 'STREPTAVIDIN_BEADS')['quantity']['value'] == pytest.approx(0.4)
    exported_run = {**_to_jsonable(result), 'ok': result.ok}
    records = final_material_records(exported_run)
    assert len(records) == 8
    assert returned['id'] in {r['container_id'] for r in records}

    # Hold belongs to the thermal program and precedes either continuation.
    completed = events(result)
    lines = CASE.read_text().splitlines()
    holds = [(i, lines[e.span.line - 1]) for i, e in enumerate(completed)
             if e.payload.get('driver_payload', {}).get('op') == 'env_hold']
    heat = next(i for i, line in holds if 'thermal_program(from = 42C' in line)
    cool = next(i for i, line in holds if 'thermal = 4C, duration = 10min' in line)
    assert heat < cool
    storage = [i for i, line in holds if 'duration = 18h' in line]
    assert len(storage) == (0 if immediate else 1)
    if storage:
        assert cool < completed.index(discards(result)[-1]) < storage[0]


def test_four_spins_preserve_quantities_and_brief_capture_spin_preserves_association():
    result = execute()
    previous = None
    checked = []
    for event in events(result):
        delta = event.payload.get('material_delta', {})
        snapshot = event.payload.get('material_state_snapshot')
        if delta.get('program_kind') == 'centrifuge_program':
            before = previous['containers'][delta['source']]
            after = snapshot['containers'][delta['source']]
            for key in ('volume_uL', 'mass_mg', 'component_quantities'):
                assert before[key] == after[key]
            drive = delta['partition']['operation_contract']['program_args']['drive']
            checked.append(drive['value'])
            if drive['value'] == 100:
                assert delta['keep_source'] == 'supernatant'
                assert delta['slots']['0'] == delta['source']
                pellet = snapshot['containers'][delta['slots']['1']]
                assert pellet['volume_uL'] == 0 and pellet['mass_mg'] == 0
                assert entry(after, 'STREPTAVIDIN_BEADS')['relation'] == 'free'
                target = entry(after, 'CAPTURED_CDNA')
                assert target['relation'] == 'bead_bound'
                assert target['associated_with'] == entry(after, 'STREPTAVIDIN_BEADS')['entry_id']
        if snapshot is not None:
            previous = snapshot
    assert checked == [3000, 3000, 3000, 100]


@pytest.mark.parametrize('fixture', ['fixture_reagents_ready', 'fixture_equipment_ready', 'fixture_precipitate_present'])
def test_preconditions_block_dependent_work(fixture):
    result = execute(**{fixture: fixture == 'fixture_precipitate_present'})
    assert_stopped(result)
    assert not discards(result)
    assert not workflow_status(result)['template_switch_program_completed']


@pytest.mark.parametrize('check', [1, 2, 3])
@pytest.mark.parametrize('recovers', [True, False])
def test_each_clearance_gate_requires_passing_result(check, recovers):
    result = execute(proceed_immediately=False, fixture_unclear_check=check,
                     fixture_clear_after_retry=recovers)
    assert len(discards(result)) == (3 if recovers else check - 1)
    if recovers:
        assert workflow_status(result)['storage_complete'] is True
    else:
        assert_stopped(result)
        assert workflow_status(result)['template_switch_program_completed'] is (check == 3)


@pytest.mark.parametrize('check', [1, 2, 3, 4])
@pytest.mark.parametrize('recovers', [True, False])
def test_each_resuspension_gate_rechecks_after_additional_mixing(check, recovers):
    result = execute(proceed_immediately=False, fixture_unsettled_check=check,
                     fixture_suspended_after_retry=recovers)
    checks = [d['result'] for d in result.state.artifacts['data_objects'].values()
              if 'beads_suspended' in d['result'] and d['result'].get('check_number') == check]
    assert len(checks) == 2 and checks[-1]['beads_suspended'] is recovers
    if recovers:
        assert workflow_status(result)['storage_complete'] is True
    else:
        assert_stopped(result)
        assert workflow_status(result)['template_switch_program_completed'] is (check >= 3)
        assert len(discards(result)) == (3 if check == 4 else 2)


@pytest.mark.parametrize('passed', [True, False])
def test_external_readouts_are_not_overwritten_by_fixture_defaults(passed):
    driver = HumanDriver(op_payloads={
        'phy': {'result': {'passed': passed}},
        'img': {'result': {'precipitate_present': False, 'supernatant_clear': True, 'beads_suspended': True}},
    })
    result = execute(driver, use_fixture_inputs=False, fixture_reagents_ready=not passed)
    if passed:
        assert workflow_status(result)['ready_for_amplification'] is True
    else:
        assert_stopped(result)
        assert not discards(result)
