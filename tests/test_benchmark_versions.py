"""Version selection preserves pinned inputs and separates paper/development runs."""

import hashlib
import json
from pathlib import Path
import runpy
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = runpy.run_path(str(ROOT / 'benchmarks/reproduce.py'))


class BenchmarkVersionFixture:
    def create(self, directory, role):
        import culsma
        import lark

        artifact = directory / 'modules/example'
        artifact.mkdir(parents=True)
        (artifact / 'source.md').write_text('## Steps\n\n1. Prepare a sample tube.\n')
        (artifact / 'protocol.culs').write_text(
            '// Source step S1: Prepare a sample tube.\nlet sample=tube();\nreturn sample;\n')
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        manifest = {
            'source_commit': commit, 'runtime_commit': commit,
            'runtime_package_version': culsma.__version__, 'lark_version': lark.__version__,
            'table_version': 'test-development' if role else 'test-paper',
            'artifacts': [{'path': 'modules/example', 'name': 'Example',
                           'matched_steps': 1, 'total_steps': 1, 'issues': [], 'completed_steps': 1}],
            'input_sha256': {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in artifact.iterdir()},
        }
        if role:
            manifest['evaluation_role'] = role
        marker = 'benchmark-table' if role else 'paper-table'
        (directory / 'README.md').write_text(
            f'Before\n<!-- {marker}:start -->\nold table\n<!-- {marker}:end -->\nAfter\n')
        path = directory / 'manifest.json'
        path.write_text(json.dumps(manifest))
        return path


@pytest.mark.parametrize('role', [None, 'development'])
def test_versioned_run_checks_selected_inputs_and_updates_only_selected_table(tmp_path, role):
    manifest = BenchmarkVersionFixture().create(tmp_path / 'version', role)
    published = (ROOT / 'benchmarks/README.md').read_bytes()
    output = tmp_path / 'results'
    assert BENCHMARK['reproduce'](ROOT, output, True, manifest) == 0
    summary = json.loads((output / 'summary.json').read_text())
    key = 'matches_manifest' if role else 'matches_paper'
    assert summary[key] is True
    assert ('matches_paper' in summary) is (role is None)
    assert summary['manifest_sha256'] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert summary['artifacts'][0]['execution']['completed_steps'] == 1
    text = manifest.with_name('README.md').read_text()
    assert text.startswith('Before\n') and text.endswith('After\n')
    assert '| Example | 1/1 | 100% |' in text
    assert (ROOT / 'benchmarks/README.md').read_bytes() == published
    with pytest.raises(FileExistsError):
        BENCHMARK['reproduce'](ROOT, output, manifest_path=manifest)


def test_changed_version_input_rejects_before_writing_results(tmp_path):
    manifest = BenchmarkVersionFixture().create(tmp_path / 'version', 'development')
    program = manifest.parent / 'modules/example/protocol.culs'
    program.write_text(program.read_text() + '// changed input\n')
    output = tmp_path / 'results'
    with pytest.raises(ValueError, match='input differs'):
        BENCHMARK['reproduce'](ROOT, output, manifest_path=manifest)
    assert not output.exists()


def test_development_snapshot_changes_only_elisa_program_and_preserves_source_inventory():
    benchmark = ROOT / 'benchmarks'
    old = json.loads((benchmark / 'manifest.json').read_text())
    folder = benchmark / 'versions/1.0.9-dev-ca7a098'
    new = json.loads((folder / 'manifest.json').read_text())
    assert new['input_sha256'].keys() == old['input_sha256'].keys()
    changed = {name for name, digest in old['input_sha256'].items()
               if new['input_sha256'][name] != digest}
    assert changed == {'modules/07-sandwich-elisa/protocol.culs'}
    for name, digest in new['input_sha256'].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    coverage = BENCHMARK['assess'](folder / 'modules/07-sandwich-elisa',
                                  new['runtime_commit'], new['table_version'])
    assert (coverage['matched_steps'], coverage['total_steps'], coverage['issues']) == (42, 42, [])


def test_recorded_development_results_match_frozen_manifest_and_output_hashes():
    folder = ROOT / 'benchmarks/versions/1.0.9-dev-ca7a098'
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    summary = json.loads((folder / 'summary.json').read_text())
    assert summary['matches_manifest'] is True and 'matches_paper' not in summary
    assert summary['manifest_sha256'] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert summary['runtime_commit'] == manifest['runtime_commit']
    assert summary['input_sha256'] == manifest['input_sha256']
    expected = {entry['path']: entry for entry in manifest['artifacts']}
    assert {row['artifact'] for row in summary['artifacts']} == expected.keys()
    assert summary['matched_steps'] == summary['total_steps'] == 173
    assert sum(row['execution']['completed_steps'] for row in summary['artifacts']) == 2700
    for row in summary['artifacts']:
        entry = expected[row['artifact']]
        assert row['matches_manifest'] is True
        assert row['coverage']['matched_steps'] == row['coverage']['total_steps'] == entry['total_steps']
        assert row['execution']['completed_steps'] == row['execution']['total_steps'] == entry['completed_steps']
        assert all(row['execution'][key] == 0 for key in ('failed_steps', 'skipped_steps', 'diagnostic_count'))
        for name, digest in row['output_sha256'].items():
            assert hashlib.sha256((folder / row['artifact'] / 'results' / name).read_bytes()).hexdigest() == digest
