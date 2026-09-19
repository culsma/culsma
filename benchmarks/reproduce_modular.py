"""Reproduce the versioned modular benchmark used in Patterns Section 3.5."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tools.modular_source_coverage import assess

ROOT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def reproduce(runtime, output):
    manifest = json.loads((ROOT / 'patterns-manifest.json').read_text())
    runtime = runtime.resolve()
    if git(runtime, 'rev-parse', 'HEAD') != manifest['runtime_commit']:
        raise ValueError('Runtime checkout must be at ' + manifest['runtime_commit'])
    if git(runtime, 'status', '--porcelain', '--', 'src', 'pyproject.toml'):
        raise ValueError('Runtime source or package metadata has local changes')
    actual_files = {
        str(p.relative_to(ROOT))
        for group in ('modules', 'composites')
        for d in (ROOT / group).iterdir() if d.is_dir()
        for p in d.iterdir() if p.suffix in ('.culs', '.md')
    } | {str(p.relative_to(ROOT)) for p in (ROOT / 'libraries').glob('*.culs')} | {'tools/modular_source_coverage.py'}
    if actual_files != set(manifest['input_sha256']):
        raise ValueError('Benchmark input inventory differs from the paper snapshot')
    for name, expected in manifest['input_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Benchmark input differs from paper snapshot: ' + name)
    env = dict(os.environ, PYTHONPATH=str(runtime / 'src'), PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    versions = json.loads(subprocess.check_output([
        sys.executable, '-c', 'import json,culsma,lark; print(json.dumps({"culsma":culsma.__version__,"lark":lark.__version__}))'
    ], env=env, cwd=runtime, text=True))
    if versions != {'culsma': manifest['runtime_package_version'], 'lark': manifest['lark_version']}:
        raise ValueError('Dependency versions differ from the manifest: ' + str(versions))
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in manifest['artifacts']:
        artifact = ROOT / entry['path']
        target = output / entry['path']
        target.mkdir(parents=True)
        coverage = assess(artifact, manifest['runtime_commit'], versions['culsma'])
        write_json(target / 'coverage.json', coverage)
        command = [sys.executable, '-m', 'culsma', 'run', str(artifact / 'protocol.culs'),
                   '--library-root', str(ROOT / 'libraries'), '--output', str(target / 'run.json')]
        process = subprocess.run(command, env=env, cwd=runtime, text=True, capture_output=True)
        (target / 'stdout.txt').write_text(process.stdout)
        (target / 'stderr.txt').write_text(process.stderr)
        compact = subprocess.run(command[:-2] + ['--results', str(target / 'results.json')],
                                 env=env, cwd=runtime, text=True, capture_output=True)
        (target / 'results.stderr.txt').write_text(compact.stderr)
        run = json.loads((target / 'run.json').read_text()) if (target / 'run.json').exists() else {}
        execution = run.get('report', {}).get('execution', {})
        coverage_matches = all(coverage[k] == entry[k] for k in ('matched_steps', 'total_steps', 'issues'))
        execution_matches = (process.returncode == 0 and compact.returncode == 0 and (target / 'results.json').is_file() and run.get('ok') is True and
            execution.get('ok') is True and execution.get('completed_steps') == entry['completed_steps'] and
            execution.get('total_steps') == entry['completed_steps'] and
            all(execution.get(k) == 0 for k in ('failed_steps', 'skipped_steps', 'diagnostic_count')))
        row = {'artifact': entry['path'], 'coverage': coverage, 'execution': execution,
               'matches_paper': coverage_matches and execution_matches,
               'output_sha256': {p.name: digest(p) for p in target.iterdir() if p.is_file()}}
        rows.append(row)
        print(f"{entry['path']}: {coverage['matched_steps']}/{coverage['total_steps']}; "
              f"execution {execution.get('completed_steps', 0)}/{entry['completed_steps']}; "
              f"{'PASS' if row['matches_paper'] else 'FAIL'}", flush=True)
    matched = sum(r['coverage']['matched_steps'] for r in rows)
    total = sum(r['coverage']['total_steps'] for r in rows)
    summary = {'schema': 'patterns-modular-run-v1', 'source_commit': manifest['source_commit'],
        'runtime_commit': manifest['runtime_commit'], 'python': platform.python_version(),
        'versions': versions, 'table_version': manifest['table_version'],
        'manifest_sha256': digest(ROOT / 'patterns-manifest.json'),
        'runner_sha256': digest(Path(__file__)), 'input_sha256': manifest['input_sha256'],
        'matched_steps': matched, 'total_steps': total, 'coverage_percent': 100 * matched / total,
        'matches_paper': all(r['matches_paper'] for r in rows), 'artifacts': rows}
    write_json(output / 'summary.json', summary)
    table = ['| Module | Coverage | Version |', '| --- | ---: | --- |']
    for r in rows:
        percent = r['coverage']['coverage_percent']
        label = '100%' if percent == 100 else f'{percent:.1f}%'
        table.append(f"| {r['artifact']} | {label} | {manifest['table_version']} |")
    (output / 'table.md').write_text('\n'.join(table) + '\n')
    return 0 if summary['matches_paper'] else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', required=True, type=Path, help='Clean checkout of the pinned runtime commit')
    parser.add_argument('--output', required=True, type=Path, help='New directory for results; existing directories are rejected')
    args = parser.parse_args()
    try:
        return reproduce(args.runtime_repo, args.output.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'Reproduction failed: {error}\n')

if __name__ == '__main__':
    raise SystemExit(main())
