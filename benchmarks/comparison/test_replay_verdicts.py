"""Ensure missing/unexpected evidence cannot become a capability No."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reproduce_comparison as replay


class VerdictTests(unittest.TestCase):
    def test_reviewed_negative_witness_reproduces_but_other_errors_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = {'bpl': [{'criterion': 'example', 'expected_result': 'No',
                    'scope': 'fixture', 'checks': [{'file': 'evidence.json',
                    'path': ['behavior'], 'equals': 'known unsupported operation'}]}]}
            (root / 'replay_expectations.json').write_text(json.dumps(spec))
            with patch.object(replay, 'PACKAGE', root):
                # Missing evidence is not No.
                self.assertEqual(replay.evaluate('bpl', root)[0]['result'], 'NE')
                for observation, verdict in [('known unsupported operation', 'No'),
                                             ('dependency import failed', 'NE'),
                                             ('now implemented', 'NE')]:
                    (root / 'evidence.json').write_text(json.dumps({'behavior': observation}))
                    row = replay.evaluate('bpl', root)[0]
                    self.assertEqual(row['result'], verdict)
                    self.assertEqual(row['reproduced'], verdict == 'No')
                (root / 'evidence.json').write_text('{invalid JSON')
                self.assertEqual(replay.evaluate('bpl', root)[0]['result'], 'NE')


if __name__ == '__main__':
    unittest.main()
