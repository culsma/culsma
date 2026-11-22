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


def test_current_source_and_protocol_match_manifest():
    manifest = json.loads((CASE / 'manifest.json').read_text())
    assert manifest['source_provenance']['upstream']['commit'] == '1b0dd6d8ed1f588f1c7891f7525f5b30304bcebe'
    assert load_verifier().check_retained(CASE)['ok']
    for name, expected in manifest['files_sha256'].items():
        assert sha256((CASE / name).read_bytes()).hexdigest() == expected


def load_verifier():
    spec = importlib.util.spec_from_file_location('whole_blood_verifier', CASE.parent / 'reproduce.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_and_executable_program_agree_on_three_centrifugations():
    executable = (CASE / 'protocol.culs').read_text()
    assert executable.count('with env(thermal = 4C, duration = ') == 3
    steps = [line for line in (CASE / 'source.md').read_text().splitlines() if '. Centrifuge ' in line]
    assert len(steps) == 3 and all(line.endswith('at 4 C.') for line in steps)


def test_verifier_rejects_unexecuted_program(tmp_path):
    (tmp_path / 'summary.json').write_text(json.dumps({'runtime_ok':False}))
    with pytest.raises(ValueError, match='did not succeed'):
        load_verifier().verify(tmp_path)


def test_original_program_material_accounting():
    result = execute_pipeline([CASE / 'protocol.culs'])
    assert result['summary']['runtime_ok']
    containers = result['run']['state']['artifacts']['material_state']['containers']
    volumes = {c['metadata']['allocation_name']: c['volume_uL'] for c in containers.values()}
    assert volumes['processing_well'] == 1 and volumes['collected_supernatant'] == 155
    assert volumes['lysis_waste'] == 1044 and volumes['wash_waste'] == 1000


def test_full_driver_evidence_and_checker_detects_missing_mixing(tmp_path):
    standalone = pytest.importorskip('culsma_opentrons.standalone')
    request = ProgramExecutionRequest((CASE / 'protocol.culs',),
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
    source, deck = load_verifier().prepare_inputs(CASE, tmp_path / 'inputs', 'no-cooling')
    rejected_config = json.loads(deck.read_text())
    config['reference_devices']['rotor']['profile']['temperature_range_celsius']['minimum'] = 20
    assert config == rejected_config
    request = ProgramExecutionRequest((CASE / 'protocol.culs',),
        'opentrons-simulator', deck, tmp_path)
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
    return load_verifier()


def test_constraint_inputs_keep_workflow_and_select_method(tmp_path):
    checks = load_interface_checks()
    source, deck = checks.prepare_inputs(CASE, tmp_path / "constraints", "constraints")
    clause = ' with constraint(ConstraintRequirement.LOW_CARRYOVER, ConstraintRequirement.HIGH_PRECISION)'
    assert source.read_text().replace(clause, '') == (CASE / 'protocol.culs').read_text()
    assert json.loads(deck.read_text())['transfer_policy']['precision_method']['pipette'] == 'flex_1channel_1000'
    _, deck = checks.prepare_inputs(CASE, tmp_path / "missing", "missing-method")
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
    pytest.importorskip("culsma_opentrons.standalone")
    artifacts = tmp_path / "run"
    checks.run_scenario(CASE, scenario, artifacts)
    verifier = load_verifier()
    assert verifier.verify_interfaces(artifacts, scenario)['ok']
    path = artifacts / 'run.json'
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
        verifier.verify_interfaces(artifacts, scenario)


def test_retained_check_detects_changed_inputs(tmp_path):
    import shutil
    case = tmp_path / 'case'
    shutil.copytree(CASE, case)
    shutil.copyfile(CASE.parent / 'reproduce.py', tmp_path / 'reproduce.py')
    (case / 'protocol.culs').write_text('changed')
    with pytest.raises(ValueError, match='Checksum mismatch: protocol.culs'):
        load_verifier().check_retained(case)


def test_normal_and_failure_reuse_maintained_inputs(tmp_path):
    verifier = load_verifier()
    for scenario in ('normal', 'failure'):
        assert verifier.prepare_inputs(CASE, tmp_path / scenario, scenario) == (CASE / 'protocol.culs', CASE / 'deck.json')
    with pytest.raises(ValueError, match='Unknown scenario'):
        verifier.prepare_inputs(CASE, tmp_path / 'unknown', 'unknown')
