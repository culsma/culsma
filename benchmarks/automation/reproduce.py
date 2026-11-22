"""Run and verify the automation benchmark's five software scenarios."""
import argparse
from collections import Counter
import hashlib
import json
from math import isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIOS = ('normal', 'constraints', 'missing-method', 'no-cooling', 'failure')
FAULT_STEP = 'entry.s16'
FAULT_MESSAGE = 'Injected loss of transfer completion confirmation'

class CompletionFailure:
    def __init__(self, original):
        self.original = original

    def run_prepared(self, operation):
        if operation.step_id == FAULT_STEP:
            raise RuntimeError(FAULT_MESSAGE)
        return self.original(operation)


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
    for r, drive, seconds in zip(cycles, [2000, 500, 300], [600, 300, 300]):
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



def prepare_inputs(case: Path, directory: Path, scenario: str):
    """Generate only the inputs that differ from the maintained workflow."""
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    source, deck = case / 'protocol.culs', case / 'deck.json'
    if scenario in {'normal', 'failure'}:
        return source, deck
    directory.mkdir(parents=True, exist_ok=False)
    config = json.loads(deck.read_text())
    if scenario == 'no-cooling':
        config['reference_devices']['rotor']['profile']['temperature_range_celsius']['minimum'] = 20
    else:
        program = source.read_text()
        statement = 'processing_well << [lps_medium_input:100uL];'
        if program.count(statement) != 1:
            raise ValueError('Expected exactly one stimulation-medium transfer')
        program = program.replace(statement, statement[:-1] +
            ' with constraint(ConstraintRequirement.LOW_CARRYOVER, ConstraintRequirement.HIGH_PRECISION);')
        source = directory / 'protocol.culs'
        source.write_text(program)
        if scenario == 'constraints':
            config.setdefault('transfer_policy', {})['precision_method'] = {
                'method_id': 'configured-flex-method', 'revision': '1', 'pipette': config['pipette'],
                'minimum_volume_uL': 20, 'maximum_volume_uL': 1000,
                'aspirate_flow_rate_uL_s': 25, 'dispense_flow_rate_uL_s': 40}
    deck = directory / 'deck.json'
    deck.write_text(json.dumps(config, indent=2) + '\n')
    return source, deck


def check_retained(case: Path) -> dict:
    """Validate retained inputs, results and the reproduction script against the manifest."""
    manifest = json.loads((case / 'manifest.json').read_text())
    for name, expected in manifest['files_sha256'].items():
        if hashlib.sha256((case / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch: {name}')
    results = json.loads((case / 'results.json').read_text())
    checks = results['method_and_failure_checks']['checks']
    if set(checks) != {'constraints', 'missing-method', 'failure'}:
        raise ValueError('Missing interface scenarios')
    if not all(v['ok'] for v in checks.values()):
        raise ValueError('An interface check did not pass')
    if not all(results['temperature_checks'][key]['verification']['ok'] for key in ('supported', 'unsupported')):
        raise ValueError('A temperature check did not pass')
    return {'ok': True, 'scenarios': list(SCENARIOS), 'files_checked': len(manifest['files_sha256'])}


def run_scenario(case: Path, scenario: str, artifacts: Path) -> dict:
    """Execute in a fresh directory, then check the expected success or failure."""
    from culsma.cli import write_run_artifacts
    from culsma.driver.models import ProgramExecutionRequest
    from culsma_opentrons.plugin import SimulatorSessionFactory
    from culsma_opentrons.standalone import StandaloneProgramExecutor

    class FailureSessions(SimulatorSessionFactory):
        def create(self, config, artifacts_dir, **kwargs):
            session = super().create(config, artifacts_dir, **kwargs)
            session.backend.run_prepared = CompletionFailure(session.backend.run_prepared).run_prepared
            return session

    if artifacts.exists():
        raise ValueError(f'Use a fresh artifact directory: {artifacts}')
    source, deck = prepare_inputs(case, artifacts / 'inputs', scenario)
    sessions = FailureSessions() if scenario == 'failure' else SimulatorSessionFactory()
    result = StandaloneProgramExecutor(sessions).execute(
        ProgramExecutionRequest((source,), 'opentrons-simulator', deck, artifacts))
    write_run_artifacts(result, artifacts)
    if scenario == 'normal':
        return verify(artifacts)
    if scenario == 'no-cooling':
        return verify_rejection(artifacts)
    return verify_interfaces(artifacts, scenario)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['whole-blood-lps-rbc'], default='whole-blood-lps-rbc')
    parser.add_argument('--scenario', choices=['all', *SCENARIOS], default='all')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check-only', action='store_true', help='Check retained files without running the driver')
    args = parser.parse_args()
    case = ROOT / args.case
    retained = check_retained(case)
    if args.check_only:
        print(json.dumps(retained, indent=2))
        return
    if args.output is None:
        parser.error('--output is required for simulation')
    if args.output.exists():
        parser.error('Use a fresh output directory')
    selected = SCENARIOS if args.scenario == 'all' else (args.scenario,)
    reports = {name: run_scenario(case, name, args.output.resolve() / name) for name in selected}
    (args.output / 'results.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
