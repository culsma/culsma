#!/usr/bin/env python3
"""Prepare one pinned runtime using that system's recorded Python interpreter.

Example: python3.13 setup_replay.py --system bpl
Existing source/environment directories are never overwritten. Package indexes
are required for dependencies; the three compared implementations are bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from replay_paths import PACKAGE, RUNTIME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, choices=['bpl', 'labop', 'culsma'])
    args = parser.parse_args()
    spec = json.loads((PACKAGE / 'sources/manifest.json').read_text())[args.system]
    if '.'.join(map(str, sys.version_info[:3])) != spec['python']:
        parser.error('Use Python ' + spec['python'] + ' for ' + args.system)
    source = RUNTIME / (args.system + '-source')
    environment = RUNTIME / (args.system + '-env')
    if source.exists() or environment.exists():
        parser.error('Runtime already exists; run reproduce_comparison.py to verify/reuse it. Nothing overwritten.')
    archive = PACKAGE / 'sources' / spec['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec['sha256']:
        raise ValueError('Source archive checksum mismatch')
    source.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts[1:]
            if not parts or member.isdir():
                continue
            if '..' in parts or not member.isfile():
                raise ValueError('Unexpected source archive member: ' + member.name)
            path = source.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle.extractfile(member).read())
            path.chmod(member.mode & 0o777)
    subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
    python = environment / 'bin/python'
    commands = [[python, '-m', 'pip', 'install', '--no-deps', 'lark==1.3.1']] if args.system == 'culsma' else [
        [python, '-m', 'pip', 'install', '--no-deps', '-r',
         PACKAGE / ('bpl-cli-requirements.txt' if args.system == 'bpl' else 'labop-requirements.txt')],
        [python, '-m', 'pip', 'install', '--no-deps', source]]
    commands.append([python, '-m', 'pip', 'check'])
    log = RUNTIME / (args.system + '-setup.txt')
    with log.open('w') as stream:
        for command in commands:
            stream.write(json.dumps(list(map(str, command))) + '\n'); stream.flush()
            subprocess.run(list(map(str, command)), check=True, stdout=stream, stderr=subprocess.STDOUT)
    print('Prepared ' + args.system + '; installation log: ' + str(log))


if __name__ == '__main__':
    main()
