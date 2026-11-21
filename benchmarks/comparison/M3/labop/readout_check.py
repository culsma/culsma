"""Query observation coordinates and sample histories on native/extended routes."""
import argparse
import json
from pathlib import Path


def trace_paths(sample, parents, visited=()):
    if sample in visited:
        raise ValueError('Cycle in sample history')
    if not parents.get(sample):
        return [{'samples': [sample], 'edges': []}]
    paths = []
    for source, label in parents[sample]:
        for path in trace_paths(source, parents, (*visited, sample)):
            paths.append({'samples': [sample, *path['samples']], 'edges': [label, *path['edges']]})
    return paths


def fraction_roles(paths):
    # These labels are emitted by the explicit FractionationUpdater extension.
    # A well name, transfer order or generic lysate ancestor is not a fraction label.
    return sorted({label.split(':', 1)[1].split('@', 1)[0]
                   for path in paths for label in path['edges']
                   if label.startswith('ClarifyLysate:')})


def fraction_parents(paths):
    return sorted({path['samples'][index + 1]
                   for path in paths for index, label in enumerate(path['edges'])
                   if label.startswith('ClarifyLysate:')})


def inspect_readouts(directory, extended=False):
    import xarray as xr
    status = json.loads((directory / ('run-status.json' if extended else 'results.json')).read_text())
    if not status['completed_normally'] or status['validation_errors']:
        raise ValueError('Execution did not complete normally')
    graph = xr.Dataset.from_dict(json.loads((directory / 'sample_graph.json').read_text()))
    data = xr.Dataset.from_dict(json.loads((directory / 'readings.json').read_text()))
    readings = data[status['fluorescence_data']]
    if readings.sizes['container'] != 1:
        raise ValueError('This witness expects one measurement plate')
    parents = {}
    for source, target, label in graph.edges.values.tolist():
        parents.setdefault(target, []).append((source, label))
    container = readings.container.item()
    wells = {}
    # Measurement is terminal in both programs, so the final well state is the measured state.
    for well in readings.location.values.tolist():
        history = graph.sel(container=container, location=well).sortby('tick')
        tick = history.sample_location.dropna('tick').tick[-1].item()
        state = history.sel(tick=tick)
        sample = state.sample_location.item()
        paths = trace_paths(sample, parents)
        wells[well] = {'observation_dataset': readings.name, 'coordinate': well,
                      'container': container, 'sample': sample,
                      'signal': readings.sel(container=container, location=well).item(),
                      'volume_uL': float(state.contents.sum().item()),
                      'fractions': fraction_roles(paths), 'fraction_parents': fraction_parents(paths),
                      'paths': paths,
                      'has_provision_ancestry': any(label.startswith('Provision(')
                                                   for path in paths for label in path['edges'])}
    complete = (set(wells) == {'A1', 'A2', 'A3'}
                and wells['A1']['fractions'] == ['supernatant']
                and wells['A2']['fractions'] == ['pellet']
                and len(wells['A1']['fraction_parents']) == 1
                and wells['A1']['fraction_parents'] == wells['A2']['fraction_parents']
                and wells['A3']['fractions'] == [])
    return {'method': 'Join readout coordinates to the terminal well state and query sample-graph edges.',
            'runtime_extension_used': extended, 'observation_count': len(wells),
            'fraction_outputs': status.get('fraction_outputs', status.get('fraction_output_names', [])),
            'wells': wells, 'two_fraction_readout_link_complete': complete}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--extended', action='store_true')
    args = parser.parse_args()
    args.output.write_text(json.dumps(inspect_readouts(args.directory, args.extended), indent=2) + '\n')
