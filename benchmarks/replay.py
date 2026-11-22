#!/usr/bin/env python3
"""Prepare isolated environments and reproduce the paper's software evaluations.

Run with Python >=3.10; downloads and environment setup are automatic. Existing
programs and published results are never replaced. Network access is required
on the first run. This entry point does not operate laboratory hardware.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import venv

ROOT = Path(globals().get('__file__', 'replay.py')).resolve().parent
CACHE = ROOT / 'local-results/replay-runtime'
UV_VERSION = '0.9.11'
RELEASE = 'v1.0.11'


def run(command, **kwargs):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def environment():
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               UV_CACHE_DIR=str(CACHE / 'uv-cache'),
               UV_PYTHON_INSTALL_DIR=str(CACHE / 'python'),
               UV_PYTHON_DOWNLOADS='automatic', PIP_NO_INPUT='1',
               PIP_CACHE_DIR=str(CACHE / 'pip-cache'))
    return env


def python_in(directory):
    return directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def prepare_uv():
    bootstrap = CACHE / 'bootstrap'
    python = python_in(bootstrap)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(bootstrap)
    check = subprocess.run([str(python), '-m', 'uv', '--version'],
                           capture_output=True, text=True, env=environment())
    if check.returncode or check.stdout.strip() != 'uv ' + UV_VERSION:
        run([python, '-m', 'pip', 'install', 'uv==' + UV_VERSION], env=environment())
    return [str(python), '-m', 'uv']


def prepare_environment(uv, name, version, requirements):
    """Reuse only an environment whose requested dependency set is unchanged."""
    specification = {'python': version, 'requirements': requirements}
    key = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()[:16]
    target = CACHE / (name + '-' + key)
    receipt = target / 'replay-install.json'
    if receipt.exists() and json.loads(receipt.read_text()) == specification:
        run([*uv, 'pip', 'check', '--python', python_in(target)], env=environment())
        return python_in(target)
    if not python_in(target).exists():
        run([*uv, 'venv', '--python', version, target], env=environment())
    run([*uv, 'pip', 'install', '--python', python_in(target), *requirements], env=environment())
    run([*uv, 'pip', 'check', '--python', python_in(target)], env=environment())
    receipt.write_text(json.dumps(specification, indent=2) + '\n')
    return python_in(target)


def archive_files(data, paths):
    """Select regular files from a GitHub archive without extracting paths."""
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts[1:]
            if not parts or not member.isfile():
                continue
            if '..' in parts or Path(*parts).is_absolute():
                raise ValueError('Unsafe archive member: ' + member.name)
            name = '/'.join(parts)
            if any(name == p or name.startswith(p.rstrip('/') + '/') for p in paths):
                files[name] = bundle.extractfile(member).read()
    if not files:
        raise ValueError('No requested files in source archive')
    return files


def prepare_package():
    """A standalone invocation downloads the fixed submission package automatically."""
    global ROOT, CACHE
    if (ROOT / 'evaluations/1.0.7/manifest.json').is_file():
        return
    destination = Path.cwd() / 'culsma-reproduction'
    if destination.exists():
        raise FileExistsError('Run the existing package with: python3 ' +
                              str(destination / 'benchmarks/replay.py'))
    url = 'https://codeload.github.com/culsma/culsma/tar.gz/' + RELEASE
    print('Downloading ' + RELEASE + ' reproduction package', flush=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        files = archive_files(response.read(), ['benchmarks'])
    if 'benchmarks/replay.py' not in files:
        raise ValueError('Release package does not yet contain the reproduction entry point')
    destination.mkdir()
    for name, content in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    ROOT = destination / 'benchmarks'
    CACHE = ROOT / 'local-results/replay-runtime'


def historical_files(commit, paths):
    """Use local Git when available; ZIP downloads fetch pinned sources automatically."""
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Expected a full recorded commit: ' + commit)
    try:
        data = subprocess.check_output(['git', '-C', str(ROOT.parent), 'archive', commit, *paths],
                                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        cache = CACHE / 'archives' / (commit + '.tar.gz')
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            return archive_files(cache.read_bytes(), paths)
        url = 'https://codeload.github.com/culsma/culsma/tar.gz/' + commit
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        files = archive_files(data, paths)
        cache.write_bytes(data)
        return files
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        return {m.name: bundle.extractfile(m).read() for m in bundle.getmembers() if m.isfile()}


def benchmark_worker(version, output):
    # Only source retrieval is adapted; the existing evaluator and checks are used intact.
    sys.path.insert(0, str(ROOT))
    import evaluate
    evaluate.git_files = historical_files
    return evaluate.evaluate(ROOT / 'evaluations' / version / 'manifest.json', output)


def automation_requirements(manifest):
    core = manifest['implementations']['culsma']['commit']
    driver = manifest['driver_install']
    return [
        'culsma @ https://github.com/culsma/culsma/archive/' + core + '.zip',
        'culsma-opentrons-simulator @ ' + driver['repository'] + '/archive/' + driver['commit'] + '.zip',
        *[name + '==' + version for name, version in manifest['packages'].items()],
    ]


def run_benchmarks(uv, output):
    python = prepare_environment(uv, 'benchmark', '3.12.8', ['lark==1.3.1'])
    for version in ('1.0.7', '1.0.9', '1.0.11'):
        run([python, ROOT / 'replay.py', '--worker', version, '--output', output / version], env=environment())


def run_automation(uv, output):
    manifest = json.loads((ROOT / 'automation/whole-blood-lps-rbc/manifest.json').read_text())
    python = prepare_environment(uv, 'automation', manifest['python'], automation_requirements(manifest))
    run([python, ROOT / 'automation/reproduce.py', '--output', output], env=environment())


def run_comparison(uv, output):
    # Existing comparison runner writes beside its inputs, so replay a disposable
    # evidence copy inside this run's output, preserving the published records.
    shutil.copytree(ROOT / 'comparison', output,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    spec = importlib.util.spec_from_file_location('comparison_replay', output / 'evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = output / 'runtime'
    cases = json.loads((output / 'L1/case.json').read_text())['systems']
    for system in ('culsma', 'labop', 'bpl'):
        version = cases[system]['runtime']['python']
        # Seed pip for the existing setup routine and obtain the recorded Python automatically.
        python = prepare_environment(uv, 'comparison-python', version, ['pip==25.1.1'])
        module.setup_runtime(system, str(python), runtime)
    run([sys.executable, output / 'evaluate.py', '--runtime', runtime], env=environment())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=('benchmark', 'automation', 'comparison'),
                        help='Optional: reproduce one part instead of all three')
    parser.add_argument('--output', type=Path, help='Optional new output directory')
    parser.add_argument('--worker', choices=('1.0.7', '1.0.9', '1.0.11'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    prepare_package()
    if args.worker:
        if args.output is None:
            parser.error('Worker requires an output directory')
        return benchmark_worker(args.worker, args.output.resolve())
    output = (args.output or ROOT / 'local-results' / ('paper-replay-' +
              datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))).resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = [args.only] if args.only else ['benchmark', 'automation', 'comparison']
    reports = {}
    try:
        uv = prepare_uv()
        for name in selected:
            print('\nReproducing ' + name, flush=True)
            try:
                {'benchmark': run_benchmarks, 'automation': run_automation,
                 'comparison': run_comparison}[name](uv, output / name)
                reports[name] = {'passed': True, 'output': str(output / name)}
            except Exception as exc:
                reports[name] = {'passed': False, 'error': str(exc)}
                print(name + ' failed: ' + str(exc), file=sys.stderr, flush=True)
            (output / 'summary.json').write_text(json.dumps(reports, indent=2) + '\n')
    except Exception as exc:
        reports['setup'] = {'passed': False, 'error': str(exc)}
        print('Setup failed: ' + str(exc), file=sys.stderr, flush=True)
        (output / 'summary.json').write_text(json.dumps(reports, indent=2) + '\n')
    print('\nResults: ' + str(output / 'summary.json'), flush=True)
    return int(not reports or any(not r['passed'] for r in reports.values()))


if __name__ == '__main__':
    sys.exit(main())
