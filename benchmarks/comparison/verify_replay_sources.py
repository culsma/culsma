"""Verify bundled source archives and the code actually imported by a replay."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tarfile

from replay_paths import PACKAGE, RUNTIME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, choices=['culsma', 'labop', 'bpl'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    spec = json.loads((PACKAGE / 'sources/manifest.json').read_text())[args.system]
    archive = PACKAGE / 'sources' / spec['archive']
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != spec['sha256']:
        raise ValueError('Source archive checksum mismatch')
    report = {'system': args.system, 'pin': spec['commit'], 'archive_sha256': actual,
              'python': sys.version, 'files': {}, 'mismatches': []}
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.isfile():
                continue
            name = member.name.split('/', 1)[1]
            name_in_package = name.removeprefix('src/') if args.system == 'culsma' else name
            module_name = name_in_package.split('/')[0]
            if module_name not in spec['packages'] or Path(name).suffix not in ('.py', '.ttl', '.lark'):
                continue
            root = Path(importlib.import_module(module_name).__file__).resolve().parent
            installed = root / name_in_package.split('/', 1)[1]
            expected = hashlib.sha256(bundle.extractfile(member).read()).hexdigest()
            observed = hashlib.sha256(installed.read_bytes()).hexdigest() if installed.exists() else None
            source = RUNTIME / (args.system + '-source') / name
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None
            # Upstream setup.py explicitly excludes *attic packages.
            excluded = args.system == 'labop' and '/attic/' in name
            report['files'][name] = {'sha256': expected, 'installed': str(installed),
                                    'excluded_by_upstream_packaging': excluded,
                                    'installed_matches': observed == expected,
                                    'source_matches': source_hash == expected}
            if (not excluded and observed != expected) or source_hash != expected:
                report['mismatches'].append(name)
    report['verified'] = bool(report['files']) and not report['mismatches']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'verified': report['verified'], 'files': len(report['files']),
                      'mismatches': report['mismatches']}))
    return 0 if report['verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
