"""Identify the actual readout obstruction in the BPL simulation trace."""
import json
from pathlib import Path


def inspect_readouts(report, trace):
    operations = {row['step_id']: row for row in report['operations']}
    traces = {row['step_id']: row for row in trace['step_traces']}
    if not report['default']['success'] or not report['cli_api_operations_match']:
        raise ValueError('Execution or CLI/API consistency failed')
    measurement = [key for key, row in operations.items() if row['source_intent'] == 'measure']
    separation = [key for key, row in operations.items() if row['source_intent'] == 'centrifuge']
    if len(measurement) != 1 or len(separation) != 1:
        raise ValueError('The shared task must contain both separation and measurement')
    skipped = []
    for key, row in operations.items():
        event = traces[key]
        if event['details'].get('unsupported'):
            skipped.append({'step': key, 'operation': row['source_intent'],
                            'primitive': row['primitive_type'],
                            'state_unchanged': event['state_before_hash'] == event['state_after_hash']})
    for key in [*measurement, *separation]:
        event = traces[key]
        if not (event['details'].get('unsupported')
                and event['details'].get('action') == 'unsupported_no_op'
                and event['state_before_hash'] == event['state_after_hash']):
            raise ValueError('Separation/readout execution changed; inspect its result representation')
    # The measured operation was a recorded unsupported no-op, so no measurement
    # record was emitted. Do not manufacture observations from the well volumes.
    return {'method': 'Inspect CLI-lowered operations and their simulator step traces.',
            'runtime_extension_used': False, 'observation_count': 0,
            'two_fraction_readout_link_complete': False,
            'skipped_operations': skipped,
            'wells': {well: {'volume_uL': report['default']['well_volumes_uL'][well],
                             'components': report['default']['well_components'][well],
                             'observation': None, 'fractions': []}
                      for well in ('A1', 'A2', 'A3')},
            'strict_execution_succeeded': report['strict']['success']}


if __name__ == '__main__':
    directory = Path(__file__).resolve().parent
    result = inspect_readouts(json.loads((directory / 'results.json').read_text()),
                              json.loads((directory / 'default_trace.json').read_text()))
    (directory / 'readout_lineage.json').write_text(json.dumps(result, indent=2) + '\n')
