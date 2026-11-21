"""Join terminal fluorescence records to their recorded separation products."""
import json
from pathlib import Path


def trace(container, before, transfers, separation):
    paths = []
    delta = separation['payload']['material_delta']
    for event, move in transfers.get(container, []):
        if event['seq'] >= before:
            continue
        if 'selected_slot' in move:
            if move['source'] != delta['source'] or event['seq'] <= separation['seq']:
                raise ValueError('Selected fraction does not belong to the recorded separation')
            paths.append({'fraction': delta['partition']['slot_contract'][move['selected_slot']],
                          'source': move['source'],
                          'events': [event['seq'], separation['seq']]})
        else:
            for parent in trace(move['source'], event['seq'], transfers, separation):
                paths.append({**parent, 'events': [event['seq'], *parent['events']]})
    return paths


def inspect_readouts(run, output):
    if not run['ok'] or not output['ok']:
        raise ValueError('Execution did not complete')
    artifacts = run['state']['artifacts']
    events = [e for e in run['events'] if e['kind'] == 'STEP_COMPLETED']
    separations = [e for e in events if e['payload'].get('material_delta', {}).get('op') == 'sep']
    if len(separations) != 1:
        raise ValueError('This witness expects one separation')
    transfers = {}
    for event in events:
        delta = event['payload'].get('material_delta', {})
        for move in delta.get('sources', []):
            if move['source'] != delta['target']:
                transfers.setdefault(delta['target'], []).append((event, move))
    wells = {}
    observations = output['returns']['entry']['value']['observation_ids']
    for identifier in observations:
        record = artifacts['data_objects'][identifier]
        if record['contract_kind'] != 'fluorescence':
            raise ValueError('Unexpected readout type')
        starts = [e['seq'] for e in run['events'] if e['kind'] == 'STEP_STARTED'
                  and e['step_id'] == record['step_id']]
        if len(starts) != 1:
            raise ValueError('Readout execution boundary is missing')
        container = record['resolved_sample']
        declared = record['sample_ref']['name']
        if artifacts['material_state']['bindings'][declared] != container:
            raise ValueError('Readout sample reference disagrees with the resolved material')
        state = artifacts['material_state']['containers'][container]
        well = state['metadata']['label'].removeprefix('Assay plate_')
        if well in wells:
            raise ValueError('Duplicate readout coordinate')
        paths = trace(container, starts[0], transfers, separations[0])
        wells[well] = {'observation': identifier, 'sample': container,
                      'signal': record['result']['signal'], 'volume_uL': state['volume_uL'],
                      'fractions': sorted({p['fraction'] for p in paths}), 'paths': paths}
    complete = (set(wells) == {'A1', 'A2', 'A3'}
                and wells['A1']['fractions'] == ['supernatant']
                and wells['A2']['fractions'] == ['pellet']
                and wells['A3']['fractions'] == [])
    return {'method': 'Query recorded observation references and earlier transfer/separation events.',
            'runtime_extension_used': False, 'observation_count': len(observations),
            'wells': wells, 'two_fraction_readout_link_complete': complete}


if __name__ == '__main__':
    directory = Path(__file__).resolve().parent
    result = inspect_readouts(json.loads((directory / 'run.json').read_text()),
                              json.loads((directory / 'output.json').read_text()))
    (directory / 'readout_lineage.json').write_text(json.dumps(result, indent=2) + '\n')
