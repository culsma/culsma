"""Reproduce BPL's GFP authoring, lowering, and software-simulation evidence.

No upstream changes, new handlers, hardware, or LLM calls. The public simulator
API initializes stocks; this is not a claim about CLI reagent initialization.
The documented optical property is retained as an authoring probe. A separately
labelled projection omits that property literal to inspect downstream behavior.
"""
import argparse
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
from replay_paths import PACKAGE, result_path


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def canonical(value):
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != '__type__'}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def contents(deck):
    return {f'{plate}:{well}': asdict(deck.get_well_contents(plate, well))
            for plate, wells in [('sources', ['A1', 'A2', 'A3']),
                                 ('assay', ['A1', 'A2', 'A3'])] for well in wells}


def seeded_deck():
    deck = create_deck_with_labware([('sources', LabwareType.TUBE_RACK, '1'),
                                    ('assay', LabwareType.PLATE_96, '2')])
    lysate = deck.get_well_contents('sources', 'A1')
    lysate.add_volume(160, Component(name='GFP lysate liquid', volume_ul=160))
    # Opaque metadata, not a BPL cell-count semantic type or partition rule.
    lysate.components.append(Component(name='GFP cellular material', volume_ul=0,
                                      properties={'declared_cells': 100000}))
    deck.get_well_contents('sources', 'A2').add_volume(
        100, Component(name='assay buffer', volume_ul=100))
    return deck


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=result_path('gfp-bpl'))
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source_dir = PACKAGE / 'cases/gfp'
    cli = str(Path(sys.executable).with_name('bplc'))
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    report = {'source_commit': '4e505740f5025d59ba655c6c955f83876f753007',
              'python': sys.version, 'commands': {}, 'cases': {},
              'scope': 'Documented syntax plus a labelled optical-syntax projection; '
                       'CLI lowering and public Simulator with externally initialized stocks.'}
    root = Path(bpl.__file__).resolve().parent
    report['source_sha256'] = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in ['orchestrator.py', 'grammar/bpl.lark', 'simulation/simulator.py',
                  'simulation/virtual_deck.py', 'lowering/plan_ir.py']}
    report['inputs_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(source_dir.glob('*.bpl'))}

    def run(label, arguments):
        command = [cli, *map(str, arguments)]
        r = subprocess.run(command, cwd=out, env=env, text=True,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout.txt')).write_text(r.stdout)
        (out / (label + '.stderr.txt')).write_text(r.stderr)
        row = {'command': command, 'returncode': r.returncode}
        report['commands'][label] = row
        write(out / 'results.json', report)
        return row

    for name in ['gfp_documented', 'gfp', 'gfp_transfers_only']:
        source = source_dir / (name + '.bpl')
        checked = run(name + '-check', ['check', source, '--json-errors'])
        row = report['cases'][name] = {'check_returncode': checked['returncode']}
        if checked['returncode']:
            continue
        plan_path = out / (name + '-plan.json')
        lowered = run(name + '-lower', ['lower', source, '--target', 'simulation',
                                       '--out', plan_path, '--json-errors'])
        if lowered['returncode']:
            raise RuntimeError('Unexpected lowering failure: ' + name)
        run(name + '-compose', ['compose', source, '--target', 'human',
                               '--out', out / (name + '-human.md'), '--json-errors'])
        program = BPLParser().parse(source.read_text(), filename=str(source))
        row['diagnostics'] = [d.to_dict() for d in run_semantic_gate(program, source)]
        plan = lower_program_to_plan(program, source, 'simulation')
        row['operations'] = [{'step_id': step.step_id,
                              'primitive_type': type(step.primitive).__name__,
                              'primitive': asdict(step.primitive),
                              'source_intent': step.source_intent}
                             for step in plan.steps.values()]
        # Confirm that the API simulation consumes the CLI's actual operations.
        cli_steps = json.loads(plan_path.read_text())['steps']
        row['cli_api_operations_match'] = (
            [canonical(s['primitive']) for s in cli_steps] ==
            [canonical(asdict(plan.steps[s].primitive)) for s in plan.topological_order()])
        if not row['cli_api_operations_match']:
            raise RuntimeError('CLI/API operation mismatch: ' + name)
        for strict in [False, True] if name == 'gfp' else [False]:
            mode = 'strict' if strict else 'default'
            deck = seeded_deck()
            snapshots = [{'stage': 'initial', 'contents': contents(deck)}]
            sim = Simulator(deck_state=deck, strict_capabilities=strict)
            sim.add_step_callback(lambda step, state: snapshots.append(
                {'stage': step.step_id, 'contents': contents(state)}))
            result = sim.simulate(plan)
            trace = asdict(result)
            trace.pop('final_deck_state', None)
            write(out / f'{name}-{mode}-trace.json', trace)
            write(out / f'{name}-{mode}-states.json', snapshots)
            final = contents(deck)
            well_volumes = {w: final['assay:' + w]['volume_ul'] for w in ['A1', 'A2', 'A3']}
            remaining = {'supernatant_location': final['sources:A3']['volume_ul'],
                         'pellet_suspension_location': final['sources:A1']['volume_ul'],
                         'buffer': final['sources:A2']['volume_ul']}
            row[mode] = {'success': result.success, 'status': result.status.name,
                'errors': result.validation_errors, 'warnings': result.warnings,
                'unsupported_step_count': result.unsupported_step_count,
                'unsupported_steps': [{'step_id': t.step_id,
                    'source_intent': plan.steps[t.step_id].source_intent,
                    'state_unchanged': t.state_before_hash == t.state_after_hash}
                    for t in result.step_traces if t.details.get('unsupported')],
                'well_volumes_uL': well_volumes, 'remaining_uL': remaining,
                'well_components': {w: final['assay:' + w]['components'] for w in well_volumes},
                'volume_expectations_met': list(well_volumes.values()) == [20, 20, 20]
                    and list(remaining.values()) == [140, 20, 40]}
        write(out / 'results.json', report)
    write(out / 'results.json', report)
    control = report['cases']['gfp_transfers_only']['default']
    if not control['success'] or not control['volume_expectations_met']:
        raise RuntimeError('Direct-transfer control failed; interpret no capability verdict.')
    print(json.dumps({'results': str(out / 'results.json'), 'cases': report['cases']},
                     indent=2, default=str))


if __name__ == '__main__':
    main()
