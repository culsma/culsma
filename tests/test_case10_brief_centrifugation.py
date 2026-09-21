"""Case 10 material routing and source-required continuation checks."""
from pathlib import Path

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


CASE = Path(__file__).resolve().parents[1] / 'archive/benchmarks-legacy/cases/10/protocol.culs'


def execute(driver=None, **inputs):
    arguments = ', '.join(f'{key} = {str(value).lower()}' for key, value in inputs.items())
    source = CASE.read_text().replace(
        'EvercodeWTMegaV3_RunSection2_1Batch();',
        f'EvercodeWTMegaV3_RunSection2_1Batch({arguments});',
    )
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


def completed(result):
    return [e for e in result.events if e.kind == 'STEP_COMPLETED']


def statuses(result):
    return [d['result'] for d in result.state.artifacts['data_objects'].values()
            if 'capture_complete' in d.get('result', {})]


def assert_status(result, complete):
    assert statuses(result) == [dict(can_continue=complete, capture_complete=complete,
                                     needs_attention=not complete)]


def discards(result):
    lines = CASE.read_text().splitlines()
    return [e for e in completed(result) if 'waste <<' in lines[e.span.line - 1]]


def spins(result):
    return [e for e in completed(result)
            if e.payload.get('material_delta', {}).get('program_kind') == 'centrifuge_program']


def capture_mixing(result):
    settings = []
    for event in completed(result):
        payload = event.payload.get('driver_payload', {})
        args = payload.get('projection', {}).get('semantic_args', {})
        if payload.get('op') == 'agit' and 'rate' in args:
            def quantity(value, unit):
                if isinstance(value, str):
                    assert value.endswith(unit)
                    return float(value.removesuffix(unit))
                assert value['unit'] == unit
                return value['value']
            settings.append((quantity(args['duration'], 'min'), quantity(args['rate'], 'rpm')))
    return settings


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
def test_brief_spins_preserve_material_and_precede_use(driver_type):
    result = execute(driver_type())
    assert_status(result, True)
    previous = None
    actual = []
    for event in completed(result):
        delta = event.payload.get('material_delta', {})
        snapshot = event.payload.get('material_state_snapshot')
        if delta.get('program_kind') == 'centrifuge_program':
            assert delta['mode'] == 'contents_state'
            assert snapshot is not None and previous is not None
            before, after = previous['containers'], snapshot['containers']
            assert before.keys() == after.keys()
            for cid in before:
                for key in ('volume_uL', 'mass_mg', 'components', 'component_quantities'):
                    assert before[cid].get(key) == after[cid].get(key)
            drive = delta['partition']['operation_contract']['program_args']['drive']
            assert drive['unit'] == 'g'
            actual.append((after[delta['source']]['metadata']['label'], drive['value']))
            if driver_type is HumanDriver:
                instruction = event.payload['driver_payload']['instruction']
                assert 'centrifuge' in instruction['summary']
                duration = '8.0s' if drive['value'] == 100 else '5.0s'
                assert any(f'duration={duration}' in detail for detail in instruction['details'])
        if snapshot is not None:
            previous = snapshot
    assert actual == [('BarcodedCDNALysate', 3000), ('CaptureEnhancer', 3000),
                      ('BarcodedCDNALysate', 3000), ('BarcodedCDNALysate', 100)]
    assert len(discards(result)) == 7
    capture_spin = spins(result)[-1]
    magnetic_capture = discards(result)[4]
    assert completed(result).index(capture_spin) < completed(result).index(magnetic_capture)
    lysate = next(c for c in result.state.artifacts['material_state']['containers'].values()
                  if c['metadata']['label'] == 'BarcodedCDNALysate')
    assert any(c['content_ref'] == 'LYSATE1' and c['relation'] == 'bead_bound'
               for c in lysate['component_entries'])
    assert capture_mixing(result) == [(10, 800), (20, 800)]


@pytest.mark.parametrize('recovers', [True, False])
def test_precipitation_recheck_controls_lysate_processing(recovers):
    result = execute(fixture_precipitate_present=True,
                     fixture_precipitate_after_reheat=not recovers)
    assert_status(result, recovers)
    assert len(spins(result)) == (4 if recovers else 0)
    assert len(discards(result)) == (7 if recovers else 4)
    checks = [d for d in result.state.artifacts['data_objects'].values()
              if 'precipitate_present' in d['result']]
    assert len(checks) == 2


@pytest.mark.parametrize('recovers', [True, False])
def test_settled_beads_require_speedup_and_successful_recheck(recovers):
    result = execute(fixture_beads_suspended=False,
                     fixture_beads_suspended_after_speedup=recovers)
    assert_status(result, recovers)
    assert capture_mixing(result) == ([(10, 800), (1, 1000), (19, 1000)] if recovers
                                      else [(10, 800), (1, 1000)])
    assert len(spins(result)) == (4 if recovers else 3)
    assert len(discards(result)) == (7 if recovers else 4)


@pytest.mark.parametrize('check_number', range(1, 8))
@pytest.mark.parametrize('recovers', [True, False])
def test_each_magnetic_discard_requires_clear_supernatant(check_number, recovers):
    result = execute(fixture_unclear_check=check_number, fixture_clear_after_retry=recovers)
    assert_status(result, recovers)
    assert len(discards(result)) == (7 if recovers else check_number - 1)
    checks = [d['result'] for d in result.state.artifacts['data_objects'].values()
              if d['result'].get('check_number') == check_number]
    assert len(checks) == 2
    assert checks[-1]['supernatant_clear'] is recovers


@pytest.mark.parametrize('input_name', ['fixture_reagents_ready', 'fixture_equipment_ready'])
def test_unconfirmed_setup_stops_capture(input_name):
    result = execute(**{input_name: False})
    assert_status(result, False)
    assert not discards(result) and not spins(result)


@pytest.mark.parametrize('confirmed', [True, False])
def test_external_readouts_control_execution_without_fixture_overrides(confirmed):
    driver = HumanDriver(op_payloads={
        'phy': {'result': {'confirmed': confirmed}},
        'img': {'result': {'precipitate_present': False, 'beads_suspended': True,
                           'supernatant_clear': True}},
    })
    result = execute(driver, use_fixture_inputs=False, fixture_reagents_ready=not confirmed)
    assert_status(result, confirmed)
    assert len(discards(result)) == (7 if confirmed else 0)


def test_batch_iterations_keep_independent_status_and_material():
    result = execute(selected_lysate_count=2)
    assert statuses(result) == [dict(can_continue=True, capture_complete=True,
                                     needs_attention=False)] * 2
    assert len(discards(result)) == 14
    assert len(spins(result)) == 8
    lysates = [c for c in result.state.artifacts['material_state']['containers'].values()
               if c['metadata']['label'] == 'BarcodedCDNALysate']
    assert len(lysates) == 2
    assert lysates[0]['components'] == lysates[1]['components']
