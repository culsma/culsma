"""Reproduce constraint and execution-failure checks on the continuous example.

Fault injection lives only in this validation harness, not in the driver.
"""
import argparse
import json
from pathlib import Path

from culsma.cli import write_run_artifacts
from culsma.driver.models import ProgramExecutionRequest
from culsma_opentrons.plugin import SimulatorSessionFactory
from culsma_opentrons.standalone import StandaloneProgramExecutor

CASE = Path(__file__).resolve().parent
FAULT_STEP = 'entry.s16'
FAULT_MESSAGE = 'Injected loss of transfer completion confirmation'


class CompletionFailure:
    def __init__(self, original):
        self.original = original

    def run_prepared(self, operation):
        if operation.step_id == FAULT_STEP:
            raise RuntimeError(FAULT_MESSAGE)
        return self.original(operation)


class FailureSessions(SimulatorSessionFactory):
    def create(self, config, artifacts_dir, **kwargs):
        session = super().create(config, artifacts_dir, **kwargs)
        session.backend.run_prepared = CompletionFailure(session.backend.run_prepared).run_prepared
        return session


def prepare_constraint_inputs(directory, missing_method=False):
    """Add method requirements to the first transfer; retain all workflow operations."""
    directory.mkdir(parents=True, exist_ok=True)
    program = (CASE / 'automation.culs').read_text()
    statement = 'processing_well << [lps_medium_input:100uL];'
    if program.count(statement) != 1:
        raise ValueError('Expected exactly one stimulation-medium transfer')
    program = program.replace(statement, statement[:-1] +
        ' with constraint(ConstraintRequirement.LOW_CARRYOVER, ConstraintRequirement.HIGH_PRECISION);')
    config = json.loads((CASE / 'deck.json').read_text())
    if not missing_method:
        config.setdefault('transfer_policy', {})['precision_method'] = {
            'method_id': 'configured-flex-method', 'revision': '1', 'pipette': config['pipette'],
            'minimum_volume_uL': 20, 'maximum_volume_uL': 1000,
            'aspirate_flow_rate_uL_s': 25, 'dispense_flow_rate_uL_s': 40}
    source, deck = directory / 'constraints.culs', directory / 'deck.json'
    source.write_text(program)
    deck.write_text(json.dumps(config, indent=2) + '\n')
    return source, deck


def run_scenario(scenario, artifacts):
    if scenario not in {'failure', 'constraints', 'missing-method'}:
        raise ValueError('Unknown interface scenario')
    source, deck = CASE / 'automation.culs', CASE / 'deck.json'
    if scenario != 'failure':
        source, deck = prepare_constraint_inputs(artifacts / 'inputs', scenario == 'missing-method')
    sessions = FailureSessions() if scenario == 'failure' else SimulatorSessionFactory()
    request = ProgramExecutionRequest((source,), 'opentrons-simulator', deck, artifacts)
    result = StandaloneProgramExecutor(sessions).execute(request)
    write_run_artifacts(result, artifacts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=['failure', 'constraints', 'missing-method'])
    parser.add_argument('artifacts', type=Path)
    args = parser.parse_args()
    result = run_scenario(args.scenario, args.artifacts)
    summary = result['summary']
    report = {name: summary[name] for name in ('runtime_ok', 'device_preflight_ok', 'device_execution_started')}
    report['failures'] = [event for event in result['run']['events'] if event['kind'] == 'STEP_FAILED']
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result['summary']['runtime_ok'] else 1)


if __name__ == '__main__':
    main()
