"""Audit the continuous example and the evidence checker without altering its source."""
import importlib.util
from hashlib import sha256
from pathlib import Path
import json
import pytest
from culsma.cli import execute_pipeline, write_run_artifacts
from culsma.driver.models import ProgramExecutionRequest

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'benchmarks/automation/whole-blood-lps-rbc'


def test_source_and_protocol_match_pinned_author_revision():
    manifest = json.loads((CASE / 'source-manifest.json').read_text())
    assert manifest['commit'] == '1b0dd6d8ed1f588f1c7891f7525f5b30304bcebe'
    assert set(manifest['files']) == {
        'source.md', 'whole_blood_lps_stimulation_rbc_lysis_sequential.culs',
    }
    for name, expected in manifest['files'].items():
        assert sha256((CASE / name).read_bytes()).hexdigest() == expected['sha256']


def load_verifier():
    spec = importlib.util.spec_from_file_location('whole_blood_verifier', CASE / 'verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simulation_changes_only_three_centrifugation_temperatures():
    original = (CASE / 'whole_blood_lps_stimulation_rbc_lysis_sequential.culs').read_text()
    adapted = (CASE / 'automation.culs').read_text()
    original_code = '\n'.join(line for line in original.splitlines() if not line.startswith('//'))
    adapted_code = '\n'.join(line for line in adapted.splitlines() if not line.startswith('//'))
    assert adapted_code.count('with env(thermal = 4C, duration = ') == 3
    assert adapted_code.replace('with env(thermal = 4C, duration = ', 'with env(thermal = 20C, duration = ') == original_code
    manifest = json.loads((CASE / 'source-manifest.json').read_text())
    assert sha256((CASE / manifest['simulation']['file']).read_bytes()).hexdigest() == manifest['simulation']['sha256']


def test_verifier_rejects_unexecuted_program(tmp_path):
    (tmp_path / 'summary.json').write_text(json.dumps({'runtime_ok':False}))
    with pytest.raises(ValueError, match='did not succeed'):
        load_verifier().verify(tmp_path)


def test_original_program_material_accounting():
    result = execute_pipeline([CASE / 'whole_blood_lps_stimulation_rbc_lysis_sequential.culs'])
    assert result['summary']['runtime_ok']
    containers = result['run']['state']['artifacts']['material_state']['containers']
    volumes = {c['metadata']['allocation_name']: c['volume_uL'] for c in containers.values()}
    assert volumes['processing_well'] == 1 and volumes['collected_supernatant'] == 155
    assert volumes['lysis_waste'] == 1044 and volumes['wash_waste'] == 1000


def test_full_driver_evidence_and_checker_detects_missing_mixing(tmp_path):
    standalone = pytest.importorskip('culsma_opentrons.standalone')
    request = ProgramExecutionRequest((CASE / 'automation.culs',),
        'opentrons-simulator', CASE / 'deck.json', tmp_path)
    result = standalone.StandaloneProgramExecutor().execute(request)
    assert result['summary']['runtime_ok'], result['run']['diagnostics']
    write_run_artifacts(result, tmp_path)
    verifier = load_verifier()
    assert verifier.verify(tmp_path)['pipette_strokes'] == 22
    path = tmp_path / 'opentrons/evidence.json'
    evidence = json.loads(path.read_text())
    evidence['receipts'] = [r for r in evidence['receipts'] if r['operation_kind'] != 'pipette_mix']
    path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='Unexpected device operations'):
        verifier.verify(tmp_path)


def test_no_cooling_rejection_preserves_sample_context(tmp_path):
    standalone = pytest.importorskip('culsma_opentrons.standalone')
    config = json.loads((CASE / 'deck.json').read_text())
    rejected_config = json.loads((CASE / 'deck-no-cooling.json').read_text())
    config['reference_devices']['rotor']['profile']['temperature_range_celsius']['minimum'] = 20
    assert config == rejected_config
    request = ProgramExecutionRequest((CASE / 'automation.culs',),
        'opentrons-simulator', CASE / 'deck-no-cooling.json', tmp_path)
    result = standalone.StandaloneProgramExecutor().execute(request)
    write_run_artifacts(result, tmp_path)
    verifier = load_verifier()
    assert verifier.verify_rejection(tmp_path)['sample'] == 'processing_well'
    path = tmp_path / 'run.json'
    run = json.loads(path.read_text())
    failed = next(e for e in run['events'] if e['kind'] == 'STEP_FAILED')
    failed['payload']['gate']['env_targets'] = []
    path.write_text(json.dumps(run))
    with pytest.raises(ValueError, match='sample reference'):
        verifier.verify_rejection(tmp_path)


def load_interface_checks():
    pytest.importorskip('culsma_opentrons.standalone')
    spec = importlib.util.spec_from_file_location('whole_blood_checks', CASE / 'check_interfaces.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_constraint_inputs_keep_workflow_and_select_method(tmp_path):
    checks = load_interface_checks()
    source, deck = checks.prepare_constraint_inputs(tmp_path)
    clause = ' with constraint(ConstraintRequirement.LOW_CARRYOVER, ConstraintRequirement.HIGH_PRECISION)'
    assert source.read_text().replace(clause, '') == (CASE / 'automation.culs').read_text()
    assert json.loads(deck.read_text())['transfer_policy']['precision_method']['pipette'] == 'flex_1channel_1000'
    _, deck = checks.prepare_constraint_inputs(tmp_path, missing_method=True)
    assert 'precision_method' not in json.loads(deck.read_text())['transfer_policy']


def test_completion_failure_delegates_other_operations():
    from types import SimpleNamespace
    checks = load_interface_checks()
    calls = []
    injector = checks.CompletionFailure(calls.append)
    operation = SimpleNamespace(step_id='different-step')
    injector.run_prepared(operation)
    assert calls == [operation]
    with pytest.raises(RuntimeError, match=checks.FAULT_MESSAGE):
        injector.run_prepared(SimpleNamespace(step_id=checks.FAULT_STEP))
    assert calls == [operation]


@pytest.mark.parametrize('scenario', ['constraints', 'missing-method', 'failure'])
def test_continuous_interface_evidence_and_tamper_detection(tmp_path, scenario):
    checks = load_interface_checks()
    checks.run_scenario(scenario, tmp_path)
    verifier = load_verifier()
    assert verifier.verify_interfaces(tmp_path, scenario)['ok']
    path = tmp_path / 'run.json'
    run = json.loads(path.read_text())
    if scenario == 'constraints':
        receipt = next(r for r in run['state']['artifacts']['device_execution']['receipts'] if r.get('constraint_resolution'))
        receipt['instrument']['aspirate_flow_rate_uL_s'] = 50
    elif scenario == 'failure':
        run['state']['step_status']['entry.s17.b.s0'] = 'completed'
    else:
        next(e for e in run['events'] if e['kind'] == 'STEP_FAILED')['payload']['driver_code'] = 'UNRELATED'
    path.write_text(json.dumps(run))
    with pytest.raises(ValueError):
        verifier.verify_interfaces(tmp_path, scenario)
