"""Replay the documented let/transfer witnesses through the pinned public CLI."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    cli = str(Path(sys.executable).with_name('bplc'))
    report = {}
    for source in sorted((PACKAGE).glob('*.bpl')):
        row = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        for action in ('check', 'validate', 'lower'):
            command = [cli, action, source.name, '--json-errors']
            if action != 'check':
                command += ['--target', 'human']
            if action == 'lower':
                command += ['--out', source.stem + '-plan.json']
            run = subprocess.run(command, cwd=out, env=env, capture_output=True,
                                 text=True, timeout=90)
            label = source.stem + '-' + action
            (out / (label + '.stdout.txt')).write_text(run.stdout)
            (out / (label + '.stderr.txt')).write_text(run.stderr)
            messages = []
            for stream in (run.stdout, run.stderr):
                for line in stream.splitlines():
                    try:
                        messages.extend(json.loads(line).get('diagnostics', []))
                    except (ValueError, AttributeError):
                        pass
            row[action] = {'command': command, 'returncode': run.returncode,
                           'diagnostic_codes': [d['code'] for d in messages]}
        report[source.stem] = row
    (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
