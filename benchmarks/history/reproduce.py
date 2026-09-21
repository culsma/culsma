"""Retrospectively run a frozen benchmark against a historical release.

Program failures are observations, not a reason to abort remaining artifacts.
Infrastructure, identity and dependency errors still abort the evaluation.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, default=Path(__file__).parent / '1.0.6/manifest.json')
    p.add_argument('--runtime-repo', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    record = json.loads(a.record.read_text())
    runtime = a.runtime_repo.resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(runtime), *args], text=True).strip()
    assert git('rev-parse', 'HEAD') == record['runtime_commit'], 'Wrong runtime commit'
    assert not git('status', '--porcelain', '--', 'src', 'pyproject.toml'), 'Dirty runtime'
    frozen = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        record['benchmark_package_commit'] + ':benchmarks/manifest.json'])
    manifest = json.loads(frozen)
    for name, expected in manifest['input_sha256'].items():
        assert digest(ROOT / name) == expected, 'Changed frozen input: ' + name
    env = dict(os.environ, PYTHONPATH=str(runtime/'src'), PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    versions = json.loads(subprocess.check_output([sys.executable, '-c',
        'import json,culsma,lark; print(json.dumps({"culsma":culsma.__version__,"lark":lark.__version__}))'],
        env=env, cwd=runtime, text=True))
    assert versions == {'culsma': record['runtime_version'], 'lark': record['lark_version']}, versions
    spec = importlib.util.spec_from_file_location('coverage_checker', ROOT/'reproduce.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in manifest['artifacts']:
        target = output / entry['path']; target.mkdir(parents=True)
        coverage = checker.assess(ROOT/entry['path'], record['runtime_commit'], versions['culsma'])
        (target/'coverage.json').write_text(json.dumps(coverage, indent=2)+'\n')
        command = [sys.executable, '-m', 'culsma', 'run', str(ROOT/entry['path']/'protocol.culs'),
                   '--library-root', str(ROOT/'libraries'), '--output', str(target/'run.json')]
        with tempfile.TemporaryDirectory(prefix='culsma-history-debug-') as debug:
            result = subprocess.run(command + ['--artifacts-dir', debug], env=env, cwd=runtime,
                                    capture_output=True, text=True, timeout=180)
            diagnostics = {}
            for phase in ('validate', 'typecheck', 'plan', 'run'):
                file = Path(debug)/f'{phase}.json'
                if file.exists():
                    data = json.loads(file.read_text())
                    diagnostics[phase] = data if isinstance(data, list) else data.get('diagnostics', [])
            if diagnostics:
                (target/'diagnostics.json').write_text(json.dumps(diagnostics, indent=2)+'\n')
        for name, value in [('stdout.txt', result.stdout), ('stderr.txt', result.stderr)]:
            if value: (target/name).write_text(value)
        report = json.loads((target/'run.json').read_text()) if (target/'run.json').exists() else {}
        execution = report.get('report', {}).get('execution', {})
        ok = (result.returncode == 0 and report.get('ok') is True and execution.get('ok') is True
              and execution.get('completed_steps') == execution.get('total_steps')
              and execution.get('total_steps', 0) > 0
              and all(execution.get(k) == 0 for k in ('failed_steps','skipped_steps','diagnostic_count')))
        rows.append({'artifact':entry['path'], 'name':entry['name'], 'coverage':coverage,
                     'exit_code':result.returncode, 'completed':ok, 'execution':execution,
                     'output_sha256':{f.name:digest(f) for f in target.iterdir()}})
        print(entry['name'] + ': ' + ('completed' if ok else 'failed'), flush=True)
    summary = {'schema':'historical-compatibility-v1', **record, 'python':platform.python_version(),
               'versions':versions, 'runner_sha256':digest(Path(__file__)),
               'coverage_checker_sha256':digest(ROOT/'reproduce.py'),
               'input_sha256':manifest['input_sha256'], 'completed_programs':sum(r['completed'] for r in rows),
               'total_programs':len(rows), 'artifacts':rows}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    table=['| Module | Source steps | Structural coverage | Execution on '+record['runtime_version']+' |',
           '| --- | ---: | ---: | --- |']
    for r in rows:
        c=r['coverage']; pct='100%' if c['coverage_percent']==100 else f"{c['coverage_percent']:.1f}%"
        table.append(f"| {r['name']} | {c['matched_steps']}/{c['total_steps']} | {pct} | {'Completed' if r['completed'] else 'Failed'} |")
    (output/'table.md').write_text('\n'.join(table)+'\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
