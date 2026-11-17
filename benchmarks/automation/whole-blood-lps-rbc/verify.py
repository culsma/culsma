"""Verify saved CLI evidence for the whole-blood automation simulation."""
import argparse
from collections import Counter
import json
from math import isclose
from pathlib import Path


def verify(artifacts: Path) -> dict:
    summary = json.loads((artifacts / 'summary.json').read_text())
    if not summary['runtime_ok'] or not summary.get('device_execution_started'):
        raise ValueError('Automation execution did not succeed')
    run = json.loads((artifacts / 'run.json').read_text())
    evidence = json.loads((artifacts / 'opentrons/evidence.json').read_text())
    receipts = evidence['receipts']
    counts = Counter(r['operation_kind'] for r in receipts)
    expected = {'setup': 15, 'pipette_mix': 15, 'transfer': 6, 'centrifuge': 3, 'labware_move': 7, 'hold': 2}
    if counts != expected:
        raise ValueError(f'Unexpected device operations: {dict(counts)}')
    mixes = [r for r in receipts if r['operation_kind'] == 'pipette_mix']
    if [r['mixed_volume_uL'] for r in mixes] != [160] * 5 + [800] * 10:
        raise ValueError('Mix volumes differ from the program')
    strokes = 0
    for r in receipts:
        if r['operation_kind'] in {'pipette_mix', 'transfer'}:
            actions = r['action_results']
            if not actions or any(a['status'] != 'returned' for a in actions):
                raise ValueError('An SDK pipette action was not confirmed')
            if len(actions) != 4 * len(r['transfers']):
                raise ValueError('Incomplete SDK action observations')
            strokes += len(r['transfers'])
    if strokes != 22:
        raise ValueError('Expected 22 fresh-tip strokes, including split 1044 uL transfer')
    cycles = [r for r in receipts if r['operation_kind'] == 'centrifuge']
    for r, drive, seconds in zip(cycles, [2000, 500, 500], [600, 300, 300]):
        if (r['request']['drive_value'], r['request']['drive_unit'], r['request']['temperature_celsius'], r['request']['duration_seconds']) != (drive, 'g', 4, seconds):
            raise ValueError('Centrifuge conditions differ from the program')
        if r['cycle_settings']['temperature_celsius'] != 4 or r['modeled_temperature_celsius'] != 4:
            raise ValueError('Centrifuge settings or modeled temperature differ from 4 C')
        if not isclose(r['cycle_settings']['drive_value'], (drive / ((2 * 3.141592653589793 / 60)**2 * .1 / 9.80665))**.5):
            raise ValueError('Rotor drive conversion differs')
    holds = [r['environment']['request'] for r in receipts if r['operation_kind'] == 'hold']
    if holds != [{'temperature_celsius':37,'duration_seconds':21600,'co2_percent':5},
                 {'temperature_celsius':20,'duration_seconds':900,'co2_percent':None}]:
        raise ValueError('Incubation conditions differ from the program')
    conditioned = [r for r in receipts if r['operation_kind'] in {'pipette_mix', 'transfer'} and 'environment' in r]
    if len(conditioned) != 12 or any(r['environment']['request']['temperature_celsius'] != 20 for r in conditioned):
        raise ValueError('Missing 20 C transfer/mixing environment evidence')
    material = run['state']['artifacts']['material_state']
    volumes = {c['metadata']['allocation_name']: c['volume_uL'] for c in material['containers'].values()}
    if volumes != {'processing_well':1, 'lps_medium_input':0, 'lysis_buffer_input':0, 'wash_buffer_input':0,
                   'collected_supernatant':155, 'lysis_waste':1044, 'wash_waste':1000}:
        raise ValueError(f'Unexpected declared material accounting: {volumes}')
    return {'ok': True, 'mode': evidence['mode'], 'operations': dict(counts), 'pipette_strokes': strokes,
            'final_volumes_uL': volumes}


def verify_rejection(artifacts: Path) -> dict:
    """Check the no-cooling profile rejects the same sample before device actions."""
    summary = json.loads((artifacts / 'summary.json').read_text())
    if summary['runtime_ok'] or summary.get('device_execution_started') is not False or summary.get('device_preflight_ok') is not False:
        raise ValueError('Expected a preflight rejection without device execution')
    run = json.loads((artifacts / 'run.json').read_text())
    failed = [e for e in run['events'] if e['kind'] == 'STEP_FAILED']
    if len(failed) != 1:
        raise ValueError('Expected one rejected centrifugation')
    event = failed[0]
    payload = event['payload']
    if payload.get('driver_code') != 'DRV_OT_CENTRIFUGE_TEMPERATURE_RANGE':
        raise ValueError('Expected a centrifuge temperature rejection')
    detail = payload['driver_payload']
    if detail.get('phase') != 'preflight' or detail.get('message') != 'Requested 4 °C is outside 20–40 °C':
        raise ValueError('Missing requested temperature and configured limits')
    gate = payload['gate']
    if gate['env']['thermal']['value'] != 4 or [t['name'] for t in gate['env_targets']] != ['processing_well']:
        raise ValueError('Rejection lost the temperature or sample reference')
    step_id = event['step_id']
    plan = json.loads((artifacts / 'plan.json').read_text())
    step = next(s for p in plan['plans'] for s in p['steps'] if s['step_id'] == step_id)
    if step['op'] != 'sep' or step['args']['sample']['name'] != 'processing_well':
        raise ValueError('Rejection does not link to the sample centrifugation')
    diagnostics = [d for d in run['diagnostics'] if d['node_id'] == step_id]
    if not diagnostics or not event.get('span') or any(d['span'] != event['span'] for d in diagnostics):
        raise ValueError('Missing source-linked diagnostic')
    execution = run['state']['artifacts']['device_execution']
    if execution['mode'] != 'preflight' or execution['receipts']:
        raise ValueError('Rejected preflight must not have device receipts')
    if run['state']['step_status'][step_id] != 'failed' or any(e['kind'] == 'STEP_COMPLETED' and e['step_id'] == step_id for e in run['events']):
        raise ValueError('Rejected separation was reported as successful')
    return {'ok': True, 'mode': 'preflight_rejection', 'step_id': step_id,
            'sample': 'processing_well', 'source_line': event['span']['line'],
            'code': payload['driver_code'], 'message': detail['message'],
            'device_execution_started': False}


def verify_interfaces(artifacts: Path, scenario: str) -> dict:
    """Check method execution, method rejection, or the injected completion loss."""
    summary = json.loads((artifacts / 'summary.json').read_text())
    run = json.loads((artifacts / 'run.json').read_text())
    execution = run['state']['artifacts']['device_execution']
    if scenario == 'constraints':
        verify(artifacts)
        receipt = next(r for r in execution['receipts'] if r.get('constraint_resolution'))
        methods = {m['requirement']: m for m in receipt['constraint_resolution']}
        if set(methods) != {'low_carryover', 'high_precision'}:
            raise ValueError('Missing method requirement resolution')
        if methods['low_carryover']['method_id'] != 'fresh-tip-per-stroke' or methods['high_precision']['method_id'] != 'configured-flex-method':
            raise ValueError('Unexpected selected method')
        if (receipt['instrument']['aspirate_flow_rate_uL_s'], receipt['instrument']['dispense_flow_rate_uL_s']) != (25, 40):
            raise ValueError('Configured method flow rates were not applied')
        return {'ok': True, 'scenario': scenario, 'step_id': receipt['step_id'],
                'methods': receipt['constraint_resolution'], 'commands': receipt['commands']}
    if scenario not in {'failure', 'missing-method'}:
        raise ValueError('Unknown interface scenario')
    failures = [e for e in run['events'] if e['kind'] == 'STEP_FAILED']
    if summary['runtime_ok'] or len(failures) != 1:
        raise ValueError('Expected exactly one failed operation')
    event = failures[0]
    payload = event['payload']
    detail = payload['driver_payload']
    if not event.get('span') or not any(d['node_id'] == event['step_id'] and d['span'] == event['span'] for d in run['diagnostics']):
        raise ValueError('Missing source-linked diagnostic')
    if scenario == 'missing-method':
        if summary.get('device_execution_started') is not False or summary.get('device_preflight_ok') is not False or execution['receipts']:
            raise ValueError('Method rejection must precede device actions')
        if payload['driver_code'] != 'DRV_OT_CONSTRAINT_METHOD' or set(payload['gate']['constraint']['requirements']) != {'low_carryover', 'high_precision'}:
            raise ValueError('Missing constraint rejection context')
    else:
        if summary.get('device_execution_started') is not True or summary.get('device_preflight_ok') is not True:
            raise ValueError('Expected failure after successful preflight')
        if event['step_id'] != 'entry.s16' or payload['driver_code'] != 'DRV_OT_EXECUTION_UNKNOWN' or detail.get('retry_safe') is not False:
            raise ValueError('Missing execution failure or unsafe-retry indication')
        fault = detail['faults'][0]
        if fault['native_details']['message'] != 'Injected loss of transfer completion confirmation' or fault['execution_state'] != 'unknown':
            raise ValueError('Missing injected failure cause')
        plan = json.loads((artifacts / 'plan.json').read_text())
        steps = [s for p in plan['plans'] for s in p['steps']]
        index = next(i for i, s in enumerate(steps) if s['step_id'] == event['step_id'])
        later = {s['step_id'] for s in steps[index + 1:]}
        if not later or any(run['state']['step_status'][s] != 'skipped' for s in later):
            raise ValueError('A later step was not skipped')
        if any(r.get('step_id') in later for r in execution['receipts']):
            raise ValueError('A later device operation was issued')
        if any(r.get('step_id') == event['step_id'] and r['operation_kind'] == 'transfer' and r.get('outcome') == 'completed' for r in execution['receipts']):
            raise ValueError('Failed transfer was recorded as completed')
        volumes = {c['metadata']['allocation_name']: c['volume_uL'] for c in run['state']['artifacts']['material_state']['containers'].values()}
        if volumes['processing_well'] != 200 or volumes['collected_supernatant'] != 0:
            raise ValueError('Unconfirmed transfer committed material changes')
    return {'ok': True, 'scenario': scenario, 'failure': event,
            'device_execution_started': summary['device_execution_started']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('--expect-rejection', action='store_true')
    parser.add_argument('--interface', choices=['constraints', 'missing-method', 'failure'])
    args = parser.parse_args()
    result = verify_interfaces(args.artifacts, args.interface) if args.interface else (verify_rejection(args.artifacts) if args.expect_rejection else verify(args.artifacts))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
