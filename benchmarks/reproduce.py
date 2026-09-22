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
import re

ROOT = Path(__file__).resolve().parent

RULES = "modular-source-step-correspondence-v1"
SOURCE_MARKER = re.compile(r"^\s*//\s+Source step S([1-9]\d*):\s+(.+)$")
DIRECT_ALIAS = re.compile(r"^let\s+[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*;$")
WRAPPER = re.compile(r"^(?:with\b|repeat\b|if\b|else\b)")


def normalize(value: str) -> str:
    return " ".join(value.split())


def read_source_steps(path: Path) -> dict[int, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line == "## Steps"]
    if len(starts) != 1:
        raise ValueError("source must contain exactly one ## Steps section")
    rows: dict[int, str] = {}
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        match = re.fullmatch(r"([1-9]\d*)\.\s+(.+)", line)
        if match:
            rows[int(match.group(1))] = normalize(match.group(2))
        elif line.strip():
            if not rows:
                raise ValueError("text precedes the first numbered source step")
            rows[max(rows)] += " " + normalize(line)
    if list(rows) != list(range(1, len(rows) + 1)):
        raise ValueError("source steps must be consecutive from 1")
    return rows


def meaningful_region(lines: list[str], marker_index: int) -> bool:
    saw_gap = False
    for raw in lines[marker_index + 1 :]:
        if SOURCE_MARKER.match(raw):
            if saw_gap:
                return False
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            saw_gap = saw_gap or "COVERAGE GAP:" in stripped
            continue
        if stripped in {"{", "}", "};"} or WRAPPER.match(stripped):
            continue
        if DIRECT_ALIAS.fullmatch(stripped):
            return False
        return True
    return False


def assess(
    artifact_dir: Path,
    implementation: str | None,
    language_version: str | None,
) -> dict[str, object]:
    source_path = artifact_dir / "source.md"
    program_paths = sorted(artifact_dir.glob("*.culs"))
    if not program_paths:
        raise ValueError("artifact contains no .culs program files")
    expected = read_source_steps(source_path)
    occurrences: dict[int, list[dict[str, object]]] = {}
    for program_path in program_paths:
        lines = program_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = SOURCE_MARKER.match(line)
            if not match:
                continue
            step = int(match.group(1))
            occurrences.setdefault(step, []).append(
                {
                    "file": program_path.name,
                    "line": index + 1,
                    "text": normalize(match.group(2)),
                    "has_code_region": meaningful_region(lines, index),
                }
            )

    steps = []
    for step, source_text in expected.items():
        found = occurrences.get(step, [])
        if not found:
            status = "missing_comment"
        elif len(found) != 1:
            status = "duplicate_comment"
        elif found[0]["text"] != source_text:
            status = "text_mismatch"
        elif not found[0]["has_code_region"]:
            status = "no_code_region"
        else:
            status = "matched"
        steps.append(
            {
                "step": step,
                "status": status,
                "source_text": source_text,
                "occurrences": found,
            }
        )
    unknown = sorted(set(occurrences) - set(expected))
    matched = sum(row["status"] == "matched" for row in steps)
    total = len(steps)
    issues = [
        {"step": row["step"], "reason": row["status"]}
        for row in steps
        if row["status"] != "matched"
    ] + [{"step": step, "reason": "unexpected_comment"} for step in unknown]
    return {
        "schema": "modular-source-coverage-v1",
        "rules": RULES,
        "metric": "source_step_correspondence",
        "artifact": artifact_dir.name,
        "implementation": implementation,
        "language_version": language_version,
        "source_sha256": digest(source_path),
        "program_sha256": {path.name: digest(path) for path in program_paths},
        "total_steps": total,
        "matched_steps": matched,
        "coverage_percent": round(100 * matched / total, 6),
        "status": "pass" if matched == total and not unknown else "incomplete",
        "issues": issues,
    }



def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def reproduce(runtime, output, update_readme=False):
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    runtime = runtime.resolve()
    if git(runtime, 'rev-parse', 'HEAD') != manifest['runtime_commit']:
        raise ValueError('Runtime checkout must be at ' + manifest['runtime_commit'])
    if git(runtime, 'status', '--porcelain', '--', 'src', 'pyproject.toml'):
        raise ValueError('Runtime source or package metadata has local changes')
    actual_files = {
        str(p.relative_to(ROOT))
        for entry in manifest['artifacts']
        for d in [ROOT / entry['path']]
        for p in d.iterdir() if p.suffix in ('.culs', '.md')
    }
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
        target = output / entry['path'] / 'results'
        target.mkdir(parents=True)
        coverage = assess(artifact, manifest['runtime_commit'], versions['culsma'])
        write_json(target / 'coverage.json', coverage)
        command = [sys.executable, '-m', 'culsma', 'run', str(artifact / 'protocol.culs'),
                   '--output', str(target / 'run.json')]
        for module in manifest['artifacts']:
            if module['path'].startswith('modules/'):
                command[5:5] = ['--library-root', str(ROOT / module['path'])]
        process = subprocess.run(command, env=env, cwd=runtime, text=True, capture_output=True)
        if process.stdout.strip():
            (target / 'stdout.txt').write_text(process.stdout)
        if process.stderr.strip():
            (target / 'stderr.txt').write_text(process.stderr)
        compact = subprocess.run(command[:-2] + ['--results', str(target / 'results.json')],
                                 env=env, cwd=runtime, text=True, capture_output=True)
        if compact.stderr.strip():
            (target / 'results.stderr.txt').write_text(compact.stderr)
        run = json.loads((target / 'run.json').read_text()) if (target / 'run.json').exists() else {}
        execution = run.get('report', {}).get('execution', {})
        coverage_matches = all(coverage[k] == entry[k] for k in ('matched_steps', 'total_steps', 'issues'))
        execution_matches = (process.returncode == 0 and compact.returncode == 0 and (target / 'results.json').is_file() and run.get('ok') is True and
            execution.get('ok') is True and execution.get('completed_steps') == entry['completed_steps'] and
            execution.get('total_steps') == entry['completed_steps'] and
            all(execution.get(k) == 0 for k in ('failed_steps', 'skipped_steps', 'diagnostic_count')))
        row = {'artifact': entry['path'], 'name': entry['name'], 'coverage': coverage, 'execution': execution,
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
        'manifest_sha256': digest(ROOT / 'manifest.json'),
        'runner_sha256': digest(Path(__file__)), 'input_sha256': manifest['input_sha256'],
        'matched_steps': matched, 'total_steps': total, 'coverage_percent': 100 * matched / total,
        'matches_paper': all(r['matches_paper'] for r in rows), 'artifacts': rows}
    write_json(output / 'summary.json', summary)
    table = [f"Evaluated with Culsma {manifest['table_version']}.", '', '| Module | Source steps | Coverage |', '| --- | ---: | ---: |']
    for r in rows:
        percent = r['coverage']['coverage_percent']
        label = '100%' if percent == 100 else f'{percent:.1f}%'
        table.append(f"| {r['name']} | {r['coverage']['matched_steps']}/{r['coverage']['total_steps']} | {label} |")
    (output / 'table.md').write_text('\n'.join(table) + '\n')
    if update_readme:
        if not summary['matches_paper']:
            raise ValueError('README is not updated because the run differs from the manifest')
        readme = ROOT / 'README.md'
        text = readme.read_text()
        start, end = '<!-- paper-table:start -->', '<!-- paper-table:end -->'
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
            raise ValueError('README requires one ordered pair of paper-table markers')
        before, rest = text.split(start)
        _, after = rest.split(end)
        readme.write_text(before + start + '\n' + '\n'.join(table) + '\n' + end + after)
    return 0 if summary['matches_paper'] else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo', required=True, type=Path, help='Clean checkout of the pinned runtime commit')
    parser.add_argument('--output', required=True, type=Path, help='New directory for results; existing directories are rejected')
    parser.add_argument('--update-readme', action='store_true', help='Refresh the README table only after all comparisons pass')
    args = parser.parse_args()
    try:
        return reproduce(args.runtime_repo, args.output.resolve(), args.update_readme)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'Reproduction failed: {error}\n')

if __name__ == '__main__':
    raise SystemExit(main())
