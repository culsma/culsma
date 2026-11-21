#!/usr/bin/env python3
"""Run or check the eight comparison cases. Software execution only."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent
CRITERIA = ('M1', 'M2', 'M3', 'M4', 'L1', 'L2', 'L3', 'L4')
SYSTEMS = ('culsma', 'labop', 'bpl')
DEFAULT_RUNTIME = ROOT.parent / 'local-results/comparison-runtime'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_dot(graph, filename, **kwargs):
    """Keep upstream graph output without requiring a Graphviz executable."""
    path = Path(filename).with_suffix('.dot')
    path.write_text(graph.source)
    return str(path)


def command_environment(system, runtime, directory):
    env = dict(os.environ, COMPARISON_RUNTIME_DIR=str(runtime),
               PYTHONPATH=os.pathsep.join([str(directory), str(ROOT)]),
               PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONHOME', None)
    if system == 'culsma':
        env['PYTHONPATH'] += os.pathsep + str(runtime / 'culsma-source/src')
    return env


def verify_runtime(system, spec, runtime, directory):
    """Check the declared Python version and pinned files actually imported."""
    python = runtime / (system + '-env/bin/python')
    code = '''import hashlib,importlib,json,sys
from pathlib import Path
spec=json.loads(sys.argv[1]); source=Path(sys.argv[2]); system=sys.argv[3]
rows={}
for name,expected in spec['source_hashes'].items():
    original=source/name
    key=name.removeprefix('src/') if system=='culsma' else name
    module,relative=key.split('/',1)
    installed=None
    if module in spec['packages']:
        installed=Path(importlib.import_module(module).__file__).resolve().parent/relative
    matches=original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==expected
    if installed is not None:
        matches=matches and installed.is_file() and hashlib.sha256(installed.read_bytes()).hexdigest()==expected
    rows[name]={'matches':matches,'expected_sha256':expected,'source':str(original),'installed':str(installed) if installed else None}
version='.'.join(map(str,sys.version_info[:3]))
print('RESULT_JSON='+json.dumps({'python':version,'commit':spec['commit'],'files':rows,'verified':version==spec['python'] and bool(rows) and all(x['matches'] for x in rows.values())}))
'''
    result = subprocess.run([str(python), '-c', code, json.dumps(spec),
                             str(runtime / (system + '-source')), system],
                            env=command_environment(system, runtime, directory),
                            capture_output=True, text=True, timeout=120)
    rows = [json.loads(line[12:]) for line in result.stdout.splitlines()
            if line.startswith('RESULT_JSON=')]
    if result.returncode or len(rows) != 1:
        raise RuntimeError('Runtime verification failed: ' + result.stderr[-2000:])
    return rows[0]


def source_receipt(directory):
    files = [ROOT / 'evaluate.py', directory.parent / 'case.json', directory / 'requirements.txt']
    files += [p for p in directory.glob('*') if p.suffix in ('.py', '.culs', '.bpl')]
    return {os.path.relpath(path, directory): digest(path) for path in sorted(set(files))}


def execute_command(system, spec, index, directory, runtime, work):
    python = runtime / (system + '-env/bin/python')
    env = command_environment(system=system, runtime=runtime, directory=directory)
    if spec['kind'] == 'culsma':
        artifact_dir = work / ('command-' + str(index))
        artifact_dir.mkdir(parents=True, exist_ok=False)
        command = [str(python), '-m', 'culsma.cli', 'run', str(directory / spec['args'][0]),
                   '--output', str(artifact_dir / 'output.json'), '--artifacts-dir', str(artifact_dir)]
    else:
        command = [str(python), *spec['args']]
    stdout = directory / ('command-%02d.stdout.txt' % index)
    stderr = directory / ('command-%02d.stderr.txt' % index)
    with stdout.open('w') as out, stderr.open('w') as err:
        result = subprocess.run(command, cwd=directory, env=env, stdout=out, stderr=err, timeout=300)
    row = {'command': command, 'cwd': str(directory), 'returncode': result.returncode,
           'stdout': stdout.name, 'stderr': stderr.name}
    if result.returncode:
        return row
    if spec['kind'] == 'culsma':
        for path in artifact_dir.rglob('*'):
            if path.is_file():
                name = spec.get('prefix', '') + str(path.relative_to(artifact_dir)).replace('/', '_')
                shutil.copy2(path, directory / name)
    elif spec['kind'] == 'probe':
        rows = [json.loads(line[12:]) for line in stdout.read_text().splitlines()
                if line.startswith('RESULT_JSON=')]
        if len(rows) != 1:
            raise ValueError('Expected exactly one probe result in ' + str(stdout))
        write_json(directory / spec['output'], rows[0])
    return row


def assess(directory, spec, execution):
    checks = []
    for row in spec['expectations']:
        for check in row['checks']:
            observed = None
            error = None
            try:
                observed = json.loads((directory / check['file']).read_text())
                for key in check['path']:
                    observed = observed[key]
                matched = observed == check['equals']
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                matched, error = False, str(exc)
            checks.append({**check, 'observed': observed, 'matched': matched, 'error': error})
    expected = {row['expected_result'] for row in spec['expectations']}
    valid = (bool(checks) and all(row['matched'] for row in checks)
             and not execution.get('errors') and bool(execution.get('commands'))
             and all(row['returncode'] == 0 for row in execution['commands'])
             and execution.get('runtime', {}).get('verified', False))
    for name, value in execution.get('input_sha256', {}).items():
        path = directory / name
        valid = valid and path.is_file() and digest(path) == value
    valid = valid and bool(execution.get('input_sha256'))
    if len(expected) != 1:
        valid = False
    return {'method': spec['method'], 'expected_result': next(iter(expected), 'NE'),
            'result': next(iter(expected)) if valid else 'NE',
            'reproduced': bool(valid), 'checks': checks, 'errors': execution.get('errors', [])}


def run_case(criterion, system, runtime, work, check_only=False):
    directory = ROOT / criterion / system
    spec = json.loads((ROOT / criterion / 'case.json').read_text())['systems'][system]
    receipt = directory / 'commands.json'
    if check_only:
        execution = json.loads(receipt.read_text()) if receipt.exists() else {'errors': ['No execution receipt']}
    else:
        execution = {'commands': [], 'errors': []}
        # Clear the receipt first so an interrupted run cannot reuse an old success.
        write_json(receipt, execution)
        try:
            execution['runtime'] = verify_runtime(system, spec['runtime'], runtime, directory)
            if not execution['runtime']['verified']:
                raise ValueError('Pinned runtime source or Python version mismatch')
            before = source_receipt(directory)
            for index, command in enumerate(spec['commands'], 1):
                row = execute_command(system, command, index, directory, runtime, work / criterion / system)
                execution['commands'].append(row)
                write_json(receipt, execution)
                if row['returncode']:
                    raise RuntimeError('Command failed; see ' + str(directory / row['stderr']))
            changed = [name for name, value in before.items()
                       if not (directory / name).is_file() or digest(directory / name) != value]
            if changed:
                raise ValueError('Inputs changed while running: ' + ', '.join(changed))
            execution['input_sha256'] = source_receipt(directory)
        except Exception as exc:
            execution['errors'].append(str(exc))
        write_json(receipt, execution)
    result = assess(directory, spec, execution)
    write_json(directory / 'evaluation.json', result)
    return criterion, system, result


def setup_runtime(system, python, runtime):
    """Install pinned dependencies outside the comparison case directory."""
    spec = json.loads((ROOT / 'L1/case.json').read_text())['systems'][system]['runtime']
    source, environment = runtime / (system + '-source'), runtime / (system + '-env')
    if source.exists() or environment.exists():
        raise ValueError('Runtime already exists; nothing overwritten: ' + str(runtime))
    version = subprocess.check_output([python, '-c', 'import platform; print(platform.python_version())'], text=True).strip()
    if version != spec['python']:
        raise ValueError('Use Python ' + spec['python'])
    runtime.mkdir(parents=True, exist_ok=True)
    archive = runtime / (system + '-source.tar.gz')
    urllib.request.urlretrieve(spec['url'], archive)
    if spec.get('sha256') and digest(archive) != spec['sha256']:
        raise ValueError('Source archive hash mismatch')
    source.mkdir()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts[1:]
            if not parts or member.isdir():
                continue
            if '..' in parts or not member.isfile():
                raise ValueError('Unexpected archive member: ' + member.name)
            target = source.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(member).read())
            target.chmod(member.mode & 0o777)
    for name, expected in spec['source_hashes'].items():
        if digest(source / name) != expected:
            raise ValueError('Pinned source mismatch: ' + name)
    subprocess.run([python, '-m', 'venv', str(environment)], check=True)
    executable = str(environment / 'bin/python')
    subprocess.run([executable, '-m', 'pip', 'install', '--no-deps', '-r',
                    str(ROOT / 'L1' / system / 'requirements.txt')], check=True)
    if system != 'culsma':
        subprocess.run([executable, '-m', 'pip', 'install', '--no-deps', str(source)], check=True)
    subprocess.run([executable, '-m', 'pip', 'check'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=(*CRITERIA, 'all'), default='all')
    parser.add_argument('--system', choices=(*SYSTEMS, 'all'), default='all')
    parser.add_argument('--runtime', type=Path,
                        default=Path(os.environ.get('COMPARISON_RUNTIME_DIR', DEFAULT_RUNTIME)))
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--setup', choices=SYSTEMS)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    runtime = args.runtime.expanduser().resolve()
    if args.setup:
        setup_runtime(args.setup, args.python, runtime)
        return 0
    criteria = CRITERIA if args.case == 'all' else (args.case,)
    systems = SYSTEMS if args.system == 'all' else (args.system,)
    work = ROOT.parent / 'local-results/comparison-execution' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_case, c, s, runtime, work, args.check_only)
                   for c in criteria for s in systems]
        for future in as_completed(futures):
            c, s, result = future.result()
            rows.append({'criterion': c, 'system': s, **result})
            print(c, s, result['result'], '(' + result['method'] + ')', flush=True)
            for error in result['errors']:
                print('  ' + error, flush=True)
    write_json(work / 'summary.json', sorted(rows, key=lambda row: (row['criterion'], row['system'])))
    print('Summary:', work / 'summary.json')
    return int(any(not row['reproduced'] for row in rows))


if __name__ == '__main__':
    sys.exit(main())
