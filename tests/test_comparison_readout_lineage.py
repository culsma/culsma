"""Readout identity must follow recorded material edges, not well-name guesses."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'benchmarks/comparison/M3'


def load_observer(system):
    spec = importlib.util.spec_from_file_location(system + '_readout_check', ROOT / system / 'readout_check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


culsma = load_observer('culsma')
labop = load_observer('labop')
bpl = load_observer('bpl')


class CulsmaLineageTests(unittest.TestCase):
    def setUp(self):
        self.run = json.loads((ROOT / 'culsma/run.json').read_text())
        self.output = json.loads((ROOT / 'culsma/output.json').read_text())

    def test_recorded_paths_recover_both_fractions_and_exclude_blank(self):
        result = culsma.inspect_readouts(self.run, self.output)
        self.assertTrue(result['two_fraction_readout_link_complete'])
        self.assertEqual(result['wells']['A3']['paths'], [])
        sources = {p['source'] for w in ('A1', 'A2') for p in result['wells'][w]['paths']}
        self.assertEqual(len(sources), 1)

    def test_swapped_fraction_transfers_are_not_accepted(self):
        for event in self.run['events']:
            for move in event['payload'].get('material_delta', {}).get('sources', []):
                if 'selected_slot' in move:
                    move['selected_slot'] = {'0': '1', '1': '0'}[move['selected_slot']]
        result = culsma.inspect_readouts(self.run, self.output)
        self.assertFalse(result['two_fraction_readout_link_complete'])
        self.assertEqual(result['wells']['A1']['fractions'], ['pellet'])

    def test_missing_fraction_selection_is_not_inferred_from_well(self):
        for event in self.run['events']:
            for move in event['payload'].get('material_delta', {}).get('sources', []):
                move.pop('selected_slot', None)
        self.assertFalse(culsma.inspect_readouts(self.run, self.output)['two_fraction_readout_link_complete'])

    def test_transfers_after_measurement_do_not_change_measured_ancestry(self):
        event = next(e for e in self.run['events']
                     if any(m.get('selected_slot') == '0'
                            for m in e['payload'].get('material_delta', {}).get('sources', [])))
        later = copy.deepcopy(event)
        later['seq'] = max(e['seq'] for e in self.run['events']) + 1
        later['payload']['material_delta']['sources'][0]['selected_slot'] = '1'
        self.run['events'].append(later)
        self.assertTrue(culsma.inspect_readouts(self.run, self.output)['two_fraction_readout_link_complete'])

    def test_inconsistent_observation_sample_reference_is_rejected(self):
        artifacts = self.run['state']['artifacts']
        ids = self.output['returns']['entry']['value']['observation_ids']
        artifacts['data_objects'][ids[0]]['resolved_sample'] = artifacts['data_objects'][ids[1]]['resolved_sample']
        with self.assertRaisesRegex(ValueError, 'sample reference'):
            culsma.inspect_readouts(self.run, self.output)


class LabopLineageTests(unittest.TestCase):
    def test_generic_source_history_does_not_invent_fraction_identity(self):
        parents = {'A2': [('pellet_named_tube', 'Transfer(20)')],
                   'pellet_named_tube': [('original', 'Transfer(160)')]}
        paths = labop.trace_paths('A2', parents)
        self.assertEqual(paths[0]['samples'][-1], 'original')
        self.assertEqual(labop.fraction_roles(paths), [])
        self.assertEqual(labop.fraction_parents(paths), [])

    def test_explicit_extension_edges_supply_role_and_common_parent(self):
        parents = {'A1': [('sup', 'Transfer(20)')], 'A2': [('pel', 'Transfer(20)')],
                   'sup': [('original', 'ClarifyLysate:supernatant@2')],
                   'pel': [('original', 'ClarifyLysate:pellet@2')]}
        for well, role in [('A1', 'supernatant'), ('A2', 'pellet')]:
            paths = labop.trace_paths(well, parents)
            self.assertEqual(labop.fraction_roles(paths), [role])
            self.assertEqual(labop.fraction_parents(paths), ['original'])

    def test_cyclic_history_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Cycle'):
            labop.trace_paths('A', {'A': [('B', 'Transfer')], 'B': [('A', 'Transfer')]})


class BplLineageTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / 'bpl/results.json').read_text())
        self.trace = json.loads((ROOT / 'bpl/default_trace.json').read_text())

    def test_completed_volume_transfers_do_not_create_measurements(self):
        result = bpl.inspect_readouts(self.report, self.trace)
        self.assertEqual(result['observation_count'], 0)
        self.assertFalse(result['two_fraction_readout_link_complete'])
        self.assertEqual([r['operation'] for r in result['skipped_operations']],
                         ['centrifuge', 'mix', 'measure'])
        self.assertEqual(result['wells']['A1']['volume_uL'], 20)
        self.assertIsNone(result['wells']['A1']['observation'])

    def test_missing_measurement_is_an_incomplete_task_not_a_negative_witness(self):
        self.report['operations'] = [r for r in self.report['operations'] if r['source_intent'] != 'measure']
        with self.assertRaisesRegex(ValueError, 'both separation and measurement'):
            bpl.inspect_readouts(self.report, self.trace)

    def test_changed_backend_support_requires_reassessment(self):
        key = next(r['step_id'] for r in self.report['operations'] if r['source_intent'] == 'measure')
        event = next(r for r in self.trace['step_traces'] if r['step_id'] == key)
        event['details'] = {'action': 'measurement'}
        with self.assertRaisesRegex(ValueError, 'execution changed'):
            bpl.inspect_readouts(self.report, self.trace)

    def test_cli_api_disagreement_cannot_be_reported_as_capability_no(self):
        self.report['cli_api_operations_match'] = False
        with self.assertRaisesRegex(ValueError, 'consistency failed'):
            bpl.inspect_readouts(self.report, self.trace)


if __name__ == '__main__':
    unittest.main()
