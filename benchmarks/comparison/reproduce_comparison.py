#!/usr/bin/env python3
"""Replay retained comparison witnesses. No hardware or LLM calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

from replay_paths import PACKAGE, RUNTIME, REPLAY_OUTPUT


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Replay:
    def __init__(self, system, directory):
        self.system, self.out = system, directory
        self.python = RUNTIME / (system + '-env/bin/python')
        self.env = dict(os.environ, COMPARISON_RESULTS_DIR=str(directory), PYTHONPATH=str(PACKAGE))
        self.env.pop('PYTHONHOME', None)
        if system == 'culsma':
            self.env['PYTHONPATH'] += os.pathsep + str(RUNTIME / 'culsma-source/src')
        self.commands = []
        self.errors = []
        directory.mkdir(parents=True)

    def run(self, label, arguments, timeout=300):
        log = self.out / 'logs' / label
        log.parent.mkdir(exist_ok=True)
        command = list(map(str, [self.python, *arguments]))
        row = {'label': label, 'command': command, 'cwd': str(self.out),
               'PYTHONPATH': self.env['PYTHONPATH'], 'runtime_directory': str(RUNTIME),
               'timeout_seconds': timeout}
        print(self.system + ': ' + label, flush=True)
        try:
            with log.with_suffix('.stdout.txt').open('w') as stdout, log.with_suffix('.stderr.txt').open('w') as stderr:
                result = subprocess.run(command, cwd=self.out, env=self.env,
                                        stdout=stdout, stderr=stderr, timeout=timeout)
            row['returncode'] = result.returncode
            if result.returncode:
                self.errors.append(label)
        except (OSError, subprocess.TimeoutExpired) as error:
            row['runner_error'] = str(error)
            self.errors.append(label)
        self.commands.append(row)
        write(self.out / 'commands.json', self.commands)
        return row

    def script(self, name, *args, label=None):
        return self.run(label or name.removesuffix('.py'), [PACKAGE / name, *args])

    def code(self, label, code, *args):
        # Save the exact executed observer as an ordinary source file.
        path = self.out / 'inputs' / (label + '.py')
        path.parent.mkdir(exist_ok=True)
        path.write_text(code)
        return self.run(label, [path, *args])

    def culsma(self, name, source):
        target = self.out / name
        target.mkdir(parents=True, exist_ok=True)
        return self.run(name.replace('/', '-'), ['-m', 'culsma.cli', 'run', source,
                        '--output', target / 'output.json', '--artifacts-dir', target])

    def collect(self):
        self.script('verify_replay_sources.py', '--system', self.system, '--output', self.out / 'source-verification.json')
        if self.errors:
            return
        self.run('pip-freeze', ['-m', 'pip', 'freeze', '--all'])
        self.run('pip-check', ['-m', 'pip', 'check'])
        self.run('python-version', ['--version'])
        if self.system in ('culsma', 'labop'):
            import check_duration_units as units
            import check_scope as scope
            code = units.CULSMA_CHECK if self.system == 'culsma' else units.LABOP_CHECK
            self.code('duration', code, PACKAGE / 'gfp.culs')
            self.code('scope', scope.CULSMA if self.system == 'culsma' else scope.LABOP)
            for label in ('duration', 'scope'):
                log = self.out / 'logs' / (label + '.stdout.txt')
                rows = [json.loads(line[12:]) for line in log.read_text().splitlines() if line.startswith('RESULT_JSON=')]
                if len(rows) != 1:
                    raise ValueError('Missing observation: ' + label)
                write(self.out / (label + '.json'), rows[0])
        if self.system == 'culsma':
            self.culsma('l1/culsma', PACKAGE / 'cases/l1/culsma/reuse.culs')
            self.culsma('l2/culsma', PACKAGE / 'cases/l2/composition.culs')
            self.script('check_culsma_l3.py')
            self.culsma('gfp', PACKAGE / 'gfp.culs')
            self.culsma('magnetic', PACKAGE / 'magnetic.culs')
            self.code('magnetic-check',
                'import json,sys\nfrom pathlib import Path\nfrom check_magnetic import check_execution\n'
                'Path(sys.argv[2]).write_text(json.dumps(check_execution(Path(sys.argv[1])),indent=2))\n',
                self.out / 'magnetic', self.out / 'material-audit.json')
        elif self.system == 'labop':
            self.script('check_modeling.py', '--output', self.out / 'modeling')
            self.script('check_labop_diagnostics.py', '--output', self.out / 'diagnostics.json')
            self.code('material-audit',
                'import json,sys\nfrom pathlib import Path\nfrom check_magnetic import audit_library\n'
                'Path(sys.argv[2]).write_text(json.dumps(audit_library(Path(sys.argv[1])),indent=2))\n',
                RUNTIME / 'labop-source', self.out / 'material-audit.json')
            self.script('labop_l1_counterexample.py', '--output', self.out / 'l1/labop-reproduction')
            self.script('check_labop_l1_public_api.py')
            self.script('check_labop_l2.py')
            self.script('check_labop_l3.py')
            self.script('gfp_labop.py', self.out / 'gfp-labop-native')
            self.script('check_labop_gfp_references.py',
                        self.out / 'gfp-labop-native/location_continuation',
                        self.out / 'gfp-references.json')
            self.script('check_upstream_examples.py', '--system', 'labop')
        else:
            self.script('check_bpl_modeling.py')
            self.script('check_bpl_m4.py', self.out / 'bpl-m4')
            self.script('gfp_bpl.py')
            for name, cases, dest in [
                ('l1', 'l1/bpl', 'l1/bpl-cli'),
                ('l1-endpoints', 'l1/bpl_endpoint_binding', 'l1/bpl-endpoint-binding'),
                ('l2', 'l2/bpl', 'l2/bpl-cli'), ('l3', 'l3/bpl', 'l3/bpl-cli')]:
                self.script('check_bpl_l1.py', '--cases-dir', PACKAGE / 'cases' / cases,
                            '--out', self.out / dest,
                            *([] if name == 'l1' else ['--skip-upstream-readme']), label=name)
            self.script('check_bpl_l2_consumption.py')
            self.script('check_upstream_examples.py', '--system', 'bpl')
        if self.system == 'culsma':
            self.code('gfp-check',
                'import json,sys\nfrom pathlib import Path\n'
                'from check import check, ' + self.system + '_result as observe\n'
                'result=observe(Path(sys.argv[1]))\n'
                'check(result,json.loads(Path(sys.argv[2]).read_text()))\n'
                'Path(sys.argv[3]).write_text(json.dumps({"pass":True,"result":result},indent=2))\n',
                self.out / 'gfp', PACKAGE / 'expected.json', self.out / 'gfp-check.json')


def evaluate(system, out):
    """Check frozen evidence predicates; unexpected evidence requires re-review."""
    spec = json.loads((PACKAGE / 'replay_expectations.json').read_text())[system]
    results = []
    for row in spec:
        checks = []
        for check in row['checks']:
            try:
                value = json.loads((out / check['file']).read_text())
                for key in check['path']:
                    value = value[key]
                matched = value == check['equals']
                checks.append(dict(check, observed=value, matched=matched))
            except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
                checks.append(dict(check, matched=False, error=str(error)))
        reproduced = bool(checks) and all(c['matched'] for c in checks)
        results.append({**row, 'checks': checks, 'reproduced': reproduced,
                        'result': row['expected_result'] if reproduced else 'NE'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=str.lower, choices=['bpl', 'labop', 'culsma', 'all'], required=True)
    parser.add_argument('--output', type=Path, help='New directory; existing directories are never overwritten')
    args = parser.parse_args()
    out = (args.output or REPLAY_OUTPUT /
           (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + args.system)).resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Preserve the exact observer sources, examples, rules and audits used by this run.
    snapshot = out / 'observer-source'
    snapshot.mkdir()
    for path in PACKAGE.iterdir():
        if path.is_file() and path.suffix in ('.py', '.sh', '.md', '.json', '.txt', '.culs'):
            shutil.copy2(path, snapshot / path.name)
    shutil.copytree(PACKAGE / 'cases', snapshot / 'cases')
    (snapshot / 'sources').mkdir()
    shutil.copy2(PACKAGE / 'sources/manifest.json', snapshot / 'sources/manifest.json')
    write(out / 'observer-sha256.json', {str(p.relative_to(snapshot)): sha(p)
                                       for p in sorted(snapshot.rglob('*')) if p.is_file()})
    systems = ['culsma', 'labop', 'bpl'] if args.system == 'all' else [args.system]
    summary = {'scope': 'Retained M1–M4/L1–L3 witnesses and inspected routes; not universal conformance.',
               'runtime_directory': str(RUNTIME),
               'unassessed': ['L4', 'remaining implementation/continuity checks'], 'systems': {}}
    for system in systems:
        replay = Replay(system, out / system)
        try:
            replay.collect()
        except Exception:
            replay.errors.append(traceback.format_exc())
        rows = evaluate(system, replay.out)
        # Any infrastructure/control failure invalidates publication of Yes/No.
        if replay.errors:
            for row in rows:
                row['result'] = 'NE'
        summary['systems'][system] = {'runner_errors': replay.errors, 'criteria': rows}
        write(out / 'summary.json', summary)
    changed = [str(p.relative_to(snapshot)) for p in snapshot.rglob('*') if p.is_file()
               and (not (PACKAGE / p.relative_to(snapshot)).exists()
                    or sha(p) != sha(PACKAGE / p.relative_to(snapshot)))]
    summary['observer_source_changed_during_run'] = changed
    if changed:
        for report in summary['systems'].values():
            report['runner_errors'].append('Observer sources changed during the run; rerun required.')
            for row in report['criteria']:
                row['result'] = 'NE'
    write(out / 'summary.json', summary)
    lines = ['# Comparison witness replay', '', summary['scope'], '',
             'Yes/No is shown only when the retained evidence predicates reproduce. NE requires review.', '',
             '| Criterion | System | Result | Evidence reproduced | Scope |',
             '| --- | --- | --- | --- | --- |']
    for system, report in summary['systems'].items():
        for row in report['criteria']:
            lines.append(f"| {row['criterion']} | {system} | {row['result']} | {row['reproduced']} | {row['scope']} |")
    (out / 'summary.md').write_text('\n'.join(lines) + '\n')
    # Hash every generated file, including logs, inputs, models, traces and source receipt.
    write(out / 'artifacts-sha256.json', {str(p.relative_to(out)): sha(p)
          for p in sorted(out.rglob('*')) if p.is_file()})
    print('Results: ' + str(out / 'summary.md'), flush=True)
    return int(any(r['runner_errors'] or any(not c['reproduced'] for c in r['criteria'])
                   for r in summary['systems'].values()))


if __name__ == '__main__':
    sys.exit(main())
