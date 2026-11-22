"""Single-entry reproduction preserves published records and selects pinned sources."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location('paper_replay', Path(__file__).resolve().parents[1] / 'benchmarks/replay.py')
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as bundle:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    return data.getvalue()


def test_archive_filters_prefixes_and_rejects_traversal():
    data = archive({'repo/src/code.py': b'x', 'repo/src-other/leak': b'y'})
    assert replay.archive_files(data, ['src']) == {'src/code.py': b'x'}
    with pytest.raises(ValueError, match='Unsafe'):
        replay.archive_files(archive({'repo/../escape': b'x'}), ['src'])
    with pytest.raises(ValueError, match='No requested'):
        replay.archive_files(data, ['absent'])


def test_zip_download_fetches_missing_history_once(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, 'CACHE', tmp_path)
    monkeypatch.setattr(replay.subprocess, 'check_output', Mock(side_effect=FileNotFoundError()))
    response = Mock()
    response.__enter__ = Mock(return_value=io.BytesIO(archive({'repo/src/a.py': b'x'})))
    response.__exit__ = Mock(return_value=False)
    download = Mock(return_value=response)
    monkeypatch.setattr(replay.urllib.request, 'urlopen', download)
    for _ in range(2):
        assert replay.historical_files('a' * 40, ['src']) == {'src/a.py': b'x'}
    assert download.call_count == 1
    with pytest.raises(ValueError, match='full recorded commit'):
        replay.historical_files('main', ['src'])


def test_automation_uses_manifest_and_public_driver():
    manifest = json.loads((replay.ROOT / 'automation/whole-blood-lps-rbc/manifest.json').read_text())
    requirements = replay.automation_requirements(manifest)
    assert manifest['implementations']['culsma']['commit'] in requirements[0]
    assert manifest['driver_install']['commit'] in requirements[1]
    assert 'https://github.com/culsma/culsma-driver-opentrons/archive/' in requirements[1]
    assert 'lark==1.3.1' in requirements


def test_environment_isolates_active_installations(monkeypatch):
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        monkeypatch.setenv(key, 'unrelated-environment')
    env = replay.environment()
    assert all(key not in env for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'))
    assert env['UV_PYTHON_DOWNLOADS'] == 'automatic'
    assert env['PYTHONNOUSERSITE'] == '1'


def test_failed_install_never_marks_environment_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, 'CACHE', tmp_path)
    def fail(command, **kwargs):
        if 'venv' in command:
            replay.python_in(Path(command[-1])).parent.mkdir(parents=True)
            replay.python_in(Path(command[-1])).touch()
        else:
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(replay, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        replay.prepare_environment(['uv'], 'test', '3.11.11', ['package==1'])
    assert not list(tmp_path.rglob('replay-install.json'))


def test_default_runs_all_and_keeps_failure_in_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['replay.py', '--output', str(tmp_path / 'result')])
    monkeypatch.setattr(replay, 'prepare_uv', lambda: ['uv'])
    called = []
    for name in ('benchmark', 'automation', 'comparison'):
        def execute(uv, output, name=name):
            called.append(name)
            if name == 'automation':
                raise RuntimeError('installation failed')
        monkeypatch.setattr(replay, 'run_' + ('benchmarks' if name == 'benchmark' else name), execute)
    assert replay.main() == 1
    assert called == ['benchmark', 'automation', 'comparison']
    result = json.loads((tmp_path / 'result/summary.json').read_text())
    assert result['benchmark']['passed'] and result['comparison']['passed']
    assert not result['automation']['passed']
    with pytest.raises(FileExistsError):
        replay.main()


def test_comparison_runs_copy_without_changing_published_records(monkeypatch, tmp_path):
    root = tmp_path / 'benchmarks'
    case = root / 'comparison/L1'
    case.mkdir(parents=True)
    (case / 'case.json').write_text(json.dumps({'systems': {s: {'runtime': {'python': '3.11.11'}}
                                                         for s in ('culsma', 'labop', 'bpl')}}))
    script = root / 'comparison/evaluate.py'
    script.write_text('def setup_runtime(system, python, runtime):\n    pass\n')
    monkeypatch.setattr(replay, 'ROOT', root)
    monkeypatch.setattr(replay, 'prepare_environment', lambda *a: Path(sys.executable))
    calls = []
    monkeypatch.setattr(replay, 'run', lambda cmd, **kw: calls.append(cmd))
    output = tmp_path / 'result'
    replay.run_comparison(['uv'], output)
    assert calls[0][1] == output / 'evaluate.py'
    assert script.read_text() == (output / 'evaluate.py').read_text()
    assert not (root / 'comparison/runtime').exists()


def test_benchmark_versions_get_separate_output_and_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, 'prepare_environment', lambda *a: Path(sys.executable))
    calls = []
    monkeypatch.setattr(replay, 'run', lambda cmd, **kw: calls.append(cmd))
    replay.run_benchmarks(['uv'], tmp_path)
    assert [c[c.index('--worker') + 1] for c in calls] == ['1.0.7', '1.0.9', '1.0.11']
    assert all('--replace' not in c and c[-1].parent == tmp_path for c in calls)


def test_standalone_download_uses_release_and_preserves_existing_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(replay, 'ROOT', tmp_path / 'standalone')
    monkeypatch.setattr(replay, 'CACHE', tmp_path / 'cache')
    payload = archive({'repo/benchmarks/replay.py': b'# entry',
                       'repo/benchmarks/evaluations/1.0.7/manifest.json': b'{}',
                       'repo/unrelated': b'ignored'})
    response = Mock()
    response.__enter__ = Mock(return_value=io.BytesIO(payload))
    response.__exit__ = Mock(return_value=False)
    download = Mock(return_value=response)
    monkeypatch.setattr(replay.urllib.request, 'urlopen', download)
    replay.prepare_package()
    assert download.call_args.args[0].endswith('/v1.0.11')
    assert (replay.ROOT / 'replay.py').read_bytes() == b'# entry'
    assert not (replay.ROOT.parent / 'unrelated').exists()
    replay.prepare_package()
    assert download.call_count == 1
    monkeypatch.setattr(replay, 'ROOT', tmp_path / 'standalone')
    with pytest.raises(FileExistsError, match='existing package'):
        replay.prepare_package()


def test_uv_bootstrap_is_private_and_pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, 'CACHE', tmp_path)
    builder = Mock()
    monkeypatch.setattr(replay.venv, 'EnvBuilder', Mock(return_value=builder))
    monkeypatch.setattr(replay.subprocess, 'run', Mock(return_value=Mock(returncode=1, stdout='')))
    calls = []
    monkeypatch.setattr(replay, 'run', lambda cmd, **kw: calls.append(cmd))
    cmd = replay.prepare_uv()
    builder.create.assert_called_once_with(tmp_path / 'bootstrap')
    assert calls[0][-1] == 'uv==' + replay.UV_VERSION
    assert cmd[0] == str(replay.python_in(tmp_path / 'bootstrap'))


def test_successful_environment_is_reused_only_for_same_specification(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, 'CACHE', tmp_path)
    calls = []
    def execute(cmd, **kwargs):
        calls.append(cmd)
        if 'venv' in cmd:
            python = replay.python_in(Path(cmd[-1]))
            python.parent.mkdir(parents=True)
            python.touch()
    monkeypatch.setattr(replay, 'run', execute)
    first = replay.prepare_environment(['uv'], 'test', '3.11.11', ['a==1'])
    assert replay.prepare_environment(['uv'], 'test', '3.11.11', ['a==1']) == first
    second = replay.prepare_environment(['uv'], 'test', '3.11.11', ['a==2'])
    assert first != second
    assert sum('install' in cmd for cmd in calls) == 2


def test_automation_runs_existing_verifier_with_fresh_output(monkeypatch, tmp_path):
    manifest = json.loads((replay.ROOT / 'automation/whole-blood-lps-rbc/manifest.json').read_text())
    setup = Mock(return_value=Path(sys.executable))
    monkeypatch.setattr(replay, 'prepare_environment', setup)
    calls = []
    monkeypatch.setattr(replay, 'run', lambda cmd, **kw: calls.append(cmd))
    replay.run_automation(['uv'], tmp_path / 'automation')
    assert setup.call_args.args[2] == manifest['python']
    assert calls[0][1] == replay.ROOT / 'automation/reproduce.py'
    assert calls[0][-1] == tmp_path / 'automation'
