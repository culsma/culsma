"""Run the fraction-to-well fluorescence task through the pinned BPL implementation.

Stock contents are initialized through the public simulator API. No operation
handlers are added. HumanStep operations and unsupported simulation steps remain
visible in the plan and trace.
"""
from dataclasses import asdict
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import bpl
from bpl.parser import BPLParser
from bpl.orchestrator import lower_program_to_plan, run_semantic_gate
from bpl.simulation.simulator import Simulator
from bpl.simulation.virtual_deck import Component, LabwareType, create_deck_with_labware

ROOT = Path(__file__).resolve().parent


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def canonical(value):
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != '__type__'}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    return value


def contents(deck):
    return {f'{plate}:{well}': asdict(deck.get_well_contents(plate, well))
            for plate in ('sources', 'assay') for well in ('A1', 'A2', 'A3')}


def seeded_deck():
    deck = create_deck_with_labware([('sources', LabwareType.TUBE_RACK, '1'),
                                    ('assay', LabwareType.PLATE_96, '2')])
    lysate = deck.get_well_contents('sources', 'A1')
    lysate.add_volume(160, Component(name='GFP lysate liquid', volume_ul=160))
    # This is opaque initial metadata, not a BPL cell-count or partition calculation.
    lysate.components.append(Component(name='GFP cellular material', volume_ul=0,
                                      properties={'declared_cells': 100000}))
    deck.get_well_contents('sources', 'A2').add_volume(
        100, Component(name='assay buffer', volume_ul=100))
    return deck


def run_cli(label, arguments):
    command = [str(Path(sys.executable).with_name('bplc')), *map(str, arguments)]
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
    (ROOT / (label + '.stdout.txt')).write_text(result.stdout)
    (ROOT / (label + '.stderr.txt')).write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(label + ' failed; inspect its stderr record')
    return {'command': command, 'returncode': result.returncode}


def simulate(plan, strict):
    mode = 'strict' if strict else 'default'
    deck = seeded_deck()
    before = contents(deck)
    result = Simulator(deck_state=deck, strict_capabilities=strict).simulate(plan)
    trace = asdict(result)
    trace.pop('final_deck_state', None)
    write(ROOT / (mode + '_trace.json'), trace)
    final = contents(deck)
    write(ROOT / (mode + '_materials.json'), {'initial': before, 'final': final})
    wells = {well: final['assay:' + well] for well in ('A1', 'A2', 'A3')}
    return {'success': result.success, 'status': result.status.name,
            'errors': result.validation_errors, 'warnings': result.warnings,
            'unsupported_step_count': result.unsupported_step_count,
            'unsupported_primitives': result.unsupported_primitives,
            'well_volumes_uL': {well: row['volume_ul'] for well, row in wells.items()},
            'well_components': {well: row['components'] for well, row in wells.items()},
            'remaining_uL': {location: final['sources:' + location]['volume_ul']
                             for location in ('A1', 'A2', 'A3')}}


def main():
    source = ROOT / 'protocol.bpl'
    plan_file = ROOT / 'plan.json'
    report = {'source_commit': '4e505740f5025d59ba655c6c955f83876f753007',
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'initialization': 'Public simulator API; cellular content is opaque metadata.',
              'commands': []}
    report['commands'].append(run_cli('protocol-check', ['check', source, '--json-errors']))
    report['commands'].append(run_cli('protocol-lower', ['lower', source, '--target', 'simulation',
                                                       '--out', plan_file, '--json-errors']))
    program = BPLParser().parse(source.read_text(), filename=str(source))
    report['diagnostics'] = [d.to_dict() for d in run_semantic_gate(program, source)]
    plan = lower_program_to_plan(program, source, 'simulation')
    report['operations'] = [{'step_id': step.step_id, 'primitive_type': type(step.primitive).__name__,
                             'primitive': asdict(step.primitive), 'source_intent': step.source_intent}
                            for step in plan.steps.values()]
    cli_steps = json.loads(plan_file.read_text())['steps']
    report['cli_api_operations_match'] = (
        [canonical(row['primitive']) for row in cli_steps] ==
        [canonical(asdict(plan.steps[key].primitive)) for key in plan.topological_order()])
    if not report['cli_api_operations_match']:
        raise RuntimeError('CLI/API operation mismatch')
    report['default'] = simulate(plan, False)
    report['strict'] = simulate(plan, True)
    write(ROOT / 'results.json', report)


if __name__ == '__main__':
    main()
