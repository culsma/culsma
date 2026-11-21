"""A negative comparison witness is different from a failed reproduction."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'comparison_evaluate', Path(__file__).resolve().parents[1] / 'benchmarks/comparison/evaluate.py')
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


class ComparisonEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        (self.directory / 'protocol.bpl').write_text('protocol Test {}')
        (self.directory / 'results.json').write_text('{"supported": false}')
        self.case = {'method': 'execution', 'expectations': [{'expected_result': 'No',
            'checks': [{'file': 'results.json', 'path': ['supported'], 'equals': False}]}]}
        self.receipt = {'commands': [{'returncode': 0}], 'errors': [],
                        'runtime': {'verified': True}, 'input_sha256': {
                            'protocol.bpl': evaluate.digest(self.directory / 'protocol.bpl')}}

    def tearDown(self):
        self.temp.cleanup()

    def test_known_negative_result_reproduces_no(self):
        result = evaluate.assess(self.directory, self.case, self.receipt)
        self.assertEqual(result['result'], 'No')
        self.assertTrue(result['reproduced'])

    def test_missing_changed_and_malformed_evidence_is_not_no(self):
        path = self.directory / 'results.json'
        for content in (None, '{"supported": true}', '{invalid', '{}'):
            if content is None:
                path.unlink()
            else:
                path.write_text(content)
            self.assertEqual(evaluate.assess(self.directory, self.case, self.receipt)['result'], 'NE')

    def test_matching_stale_results_do_not_hide_command_or_runtime_failure(self):
        for changes in ({'commands': [{'returncode': 1}]}, {'errors': ['timeout']},
                        {'runtime': {'verified': False}}, {'input_sha256': {}}, {'commands': []}):
            with self.subTest(changes=changes):
                self.assertEqual(evaluate.assess(self.directory, self.case,
                                                {**self.receipt, **changes})['result'], 'NE')

    def test_changed_program_invalidates_retained_results(self):
        (self.directory / 'protocol.bpl').write_text('protocol Changed {}')
        self.assertEqual(evaluate.assess(self.directory, self.case, self.receipt)['result'], 'NE')

    def test_environment_keeps_case_and_runtime_imports_separate(self):
        with patch.dict('os.environ', {'PYTHONHOME': '/unexpected', 'PYTHONPATH': '/other'}, clear=True):
            env = evaluate.command_environment('culsma', self.directory / 'runtime', self.directory)
        self.assertNotIn('PYTHONHOME', env)
        self.assertNotIn('/other', env['PYTHONPATH'])
        self.assertIn(str(self.directory / 'runtime/culsma-source/src'), env['PYTHONPATH'])
        self.assertEqual(env['PYTHONDONTWRITEBYTECODE'], '1')

    def test_source_receipt_tracks_program_not_generated_results(self):
        with patch.object(evaluate, 'ROOT', self.directory):
            (self.directory / 'evaluate.py').write_text('# runner')
            (self.directory / 'case.json').write_text('{}')
            case = self.directory / 'culsma'
            case.mkdir()
            (case / 'requirements.txt').write_text('lark==1.3.1')
            (case / 'protocol.culs').write_text('return 1;')
            (case / 'results.json').write_text('{}')
            before = evaluate.source_receipt(case)
            (case / 'results.json').write_text('{"result": 1}')
            self.assertEqual(before, evaluate.source_receipt(case))
            (case / 'protocol.culs').write_text('return 2;')
            self.assertNotEqual(before, evaluate.source_receipt(case))

    def test_setup_refuses_to_overwrite_existing_runtime(self):
        with patch.object(evaluate, 'ROOT', self.directory):
            (self.directory / 'L1').mkdir()
            (self.directory / 'L1/case.json').write_text(json.dumps({'systems': {'bpl': {'runtime': {}}}}))
            (self.directory / 'bpl-source').mkdir()
            with self.assertRaisesRegex(ValueError, 'nothing overwritten'):
                evaluate.setup_runtime('bpl', 'unused-python', self.directory)


if __name__ == '__main__':
    unittest.main()
