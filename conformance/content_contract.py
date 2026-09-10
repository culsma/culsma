"""Extract the owning Markdown contract and check its frozen implementation snapshot."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

VOCABULARY = '05_operation_vocabulary_and_call_contracts.md'
DIAGNOSTICS = '06_validation_and_diagnostics.md'
MAPPING = '10_conformance_and_test_mapping.md'
SECTIONS = {
    'containers': (VOCABULARY, '### 6.2.4 Container/Carrier and Content Taxonomy'),
    'kinds': (VOCABULARY, '### 6.2.5 Canonical Content Kind Set'),
    'types': (VOCABULARY, '### 6.2.6 Canonical `content_type` and `attrs.role` Table'),
    'enums': (VOCABULARY, '### 6.2.7 Explicit Content Enum Contract'),
    'legacy': (VOCABULARY, '### 6.2.8 Selected Legacy Normalization Conformance Cases'),
    'diagnostics': (DIAGNOSTICS, '## 8.2.2 Diagnostic Mapping Table (Content + Mutation Model)'),
    'mapping': (MAPPING, '## 12.15 Content Enum Conformance Card (PM #110)'),
}
PILOT_DIAGNOSTICS = frozenset({
    'SEM_INVALID_CONTENT_KIND', 'SEM_INVALID_CONTENT_TYPE_VALUE',
    'SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED', 'SEM_SURFACE_CAPACITY_FORBIDDEN',
    'SEM_CONTENT_ENUM_MEMBER_INVALID', 'SEM_CONTENT_ENUM_BINDING_CYCLE',
    'TYPE_CONTENT_ENUM_TYPE_MISMATCH', 'TYPE_CONTENT_KIND_NOT_TEXT',
    'TYPE_CONTENT_TYPE_NOT_TEXT', 'TYPE_CONTAINER_KIND_NOT_TEXT',
    'PLAN_CONTENT_CLASSIFICATION_INVALID', 'PLAN_CONTAINER_KIND_INVALID',
    'MAT_CONTENT_CLASSIFICATION_INVALID', 'MAT_CONTAINER_KIND_INVALID', 'MAT_INVALID_CAPACITY',
})
SNAPSHOT = Path(__file__).with_name('content_reference.json')


def extract_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == heading]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one section: {heading}')
    start = matches[0]
    level = len(heading.split(' ', 1)[0])
    end = next((index for index in range(start + 1, len(lines))
                if re.match(r'^#{1,' + str(level) + r'} ', lines[index])), len(lines))
    return '\n'.join(lines[start:end]).strip() + '\n'


def table_rows(section: str, first_header: str) -> list[list[str]]:
    rows = []
    width = None
    found = False
    for line in section.splitlines():
        if not line.startswith('|'):
            if found:
                break
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if not found:
            if cells[0] == first_header:
                found, width = True, len(cells)
            continue
        if all(re.fullmatch(r':?-+:?', cell) for cell in cells):
            continue
        if len(cells) != width:
            raise ValueError(f'Malformed table row: {line}')
        rows.append(cells)
    if not found or not rows:
        raise ValueError(f'Missing or empty table: {first_header}')
    return rows


def code_tokens(text: str) -> list[str]:
    return re.findall(r'`([^`]+)`', text)


def project_contract(sections: dict[str, str]) -> dict:
    kinds = re.findall(r'^\d+\. `([^`]+)`$', sections['kinds'], re.MULTILINE)
    if not kinds or len(kinds) != len(set(kinds)):
        raise ValueError('Missing or duplicate canonical kinds')
    container_line = next((line for line in sections['containers'].splitlines()
                           if 'Concrete container kinds are' in line), '')
    containers = code_tokens(container_line)
    if not containers or len(containers) != len(set(containers)):
        raise ValueError('Missing or duplicate container kinds')
    types = {kind: [] for kind in kinds}
    roles = {}
    for row in table_rows(sections['types'], 'content_kind'):
        kind_tokens, members = code_tokens(row[0]), code_tokens(row[1])
        if len(kind_tokens) != 1 or kind_tokens[0] not in types or not members:
            raise ValueError(f'Invalid taxonomy row: {row}')
        kind = kind_tokens[0]
        for member in members:
            if member in types[kind] or any(member in values for values in types.values()):
                raise ValueError(f'Duplicate or multiply assigned content type: {member}')
            types[kind].append(member)
            roles[f'{kind}/{member}'] = code_tokens(row[2])
    fallback = {}
    for kind, members in types.items():
        candidates = [member for member in members if member.startswith('other_')]
        if len(candidates) != 1:
            raise ValueError(f'Expected one other_* fallback for {kind}')
        fallback[kind] = candidates[0]
    if 'Non-standard `attrs.role` values MAY be recorded as ordinary attr metadata' not in sections['types']:
        raise ValueError('Open attrs.role contract is missing; review semantics before changing the extractor')
    legacy = []
    for row in table_rows(sections['legacy'], 'legacy kind'):
        values = [code_tokens(cell) for cell in row]
        if any(len(value) != 1 for value in values):
            raise ValueError(f'Invalid legacy fixture: {row}')
        kind, content_type, target_kind, target_type, attrs = [value[0] for value in values]
        legacy.append({'input': [kind, content_type], 'output': [target_kind, target_type], 'attrs': json.loads(attrs)})
    diagnostics = {}
    for row in table_rows(sections['diagnostics'], 'Failure condition'):
        for code in code_tokens(row[2]):
            if code not in PILOT_DIAGNOSTICS:
                continue
            entry = {'stage': row[1], 'severity': 'warning' if row[3] == 'current warning' else 'error', 'status': row[3]}
            if row[3] not in {'current', 'current warning'}:
                raise ValueError(f'Unsupported diagnostic status: {code}: {row[3]}')
            if code in diagnostics and diagnostics[code] != entry:
                raise ValueError(f'Conflicting diagnostic ownership: {code}')
            diagnostics[code] = entry
    if set(diagnostics) != PILOT_DIAGNOSTICS:
        raise ValueError(f'Missing pilot diagnostics: {sorted(PILOT_DIAGNOSTICS - diagnostics.keys())}')
    requirements = {}
    for row in table_rows(sections['mapping'], 'Invariant'):
        if row[2] in requirements:
            raise ValueError(f'Duplicate requirement: {row[2]}')
        requirements[row[2]] = {'owner': row[1], 'test': row[3]}
    return {'container_kinds': sorted(containers), 'types_by_kind': {k: sorted(v) for k, v in types.items()},
            'fallback_by_kind': fallback, 'recommended_roles': roles, 'roles_open': True,
            'legacy_cases': legacy, 'diagnostics': diagnostics, 'requirements': requirements}


def snapshot_from_sections(sections: dict[str, str]) -> dict:
    if sections.keys() != SECTIONS.keys():
        raise ValueError('Unexpected or missing source sections')
    return {'schema_version': 1, 'source_repository': 'culsma/culsma-reference',
            'sources': {key: {'path': SECTIONS[key][0], 'heading': SECTIONS[key][1],
                              'sha256': hashlib.sha256(text.encode()).hexdigest(), 'markdown': text}
                        for key, text in sections.items()},
            'contract': project_contract(sections)}


def read_reference(root: Path) -> dict:
    return snapshot_from_sections({key: extract_section((root / file).read_text(), heading)
                                   for key, (file, heading) in SECTIONS.items()})


def validate_snapshot(snapshot: dict) -> None:
    regenerated = snapshot_from_sections({key: item['markdown'] for key, item in snapshot['sources'].items()})
    if regenerated != snapshot:
        raise ValueError('Snapshot differs from its source sections or hashes; regenerate from the owning reference')


def implementation_errors(contract: dict) -> list[str]:
    from culsma.common.content_contracts import (
        ContentKind, ContentType, ContainerKind, STANDARD_CONTENT_TYPES_BY_KIND,
        FALLBACK_CONTENT_TYPE_BY_KIND, parse_content_classification,
    )
    from culsma.pipeline.compat.content_taxonomy import normalize_content_classification

    errors = []
    comparisons = {
        'content kinds': ({member.value for member in ContentKind}, set(contract['types_by_kind'])),
        'content types': ({member.value for member in ContentType}, {t for types in contract['types_by_kind'].values() for t in types}),
        'container kinds': ({member.value for member in ContainerKind}, set(contract['container_kinds'])),
        'kind/type pairs': ({k: sorted(v) for k, v in STANDARD_CONTENT_TYPES_BY_KIND.items()}, contract['types_by_kind']),
        'fallbacks': (dict(FALLBACK_CONTENT_TYPE_BY_KIND), contract['fallback_by_kind']),
    }
    for label, (actual, expected) in comparisons.items():
        if actual != expected:
            errors.append(f'{label} differ from reference: actual={actual!r}, expected={expected!r}')
    for family in (ContentKind, ContentType, ContainerKind):
        if any(member.name != member.value.upper() for member in family):
            errors.append(f'{family.__name__} member names differ from the uppercase canonical contract')
    for kind, types in contract['types_by_kind'].items():
        for content_type in types:
            if parse_content_classification(kind, content_type) is None:
                errors.append(f'Validator rejects reference pair {kind}/{content_type}')
    for case in contract['legacy_cases']:
        actual = normalize_content_classification(*case['input'])
        if ([actual.kind, actual.type] != case['output'] or actual.attrs != case['attrs']
                or [actual.original_kind, actual.original_type] != case['input']):
            errors.append(f'Legacy normalization differs from reference: {case["input"]}')
    return errors


def requirement_hook_errors(contract: dict, root: Path) -> list[str]:
    errors = []
    if set(contract['requirements']) != {f'CNT-ENUM-0{index}' for index in range(1, 8)}:
        errors.append('Missing or extra content pilot requirement IDs')
    for requirement, entry in contract['requirements'].items():
        hooks = re.findall(r'(tests/[a-zA-Z0-9_]+\.py)(?:::(test_[a-zA-Z0-9_]+))?', entry['test'])
        if not hooks:
            errors.append(f'{requirement} has no executable test hook')
        for file, function in hooks:
            target = root / file
            if not target.is_file():
                errors.append(f'{requirement}: missing test module {file}')
            elif function:
                names = {node.name for node in ast.parse(target.read_text()).body if isinstance(node, ast.FunctionDef)}
                if function not in names:
                    errors.append(f'{requirement}: missing test {file}::{function}')
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root', type=Path)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.write:
            if args.reference_root is None:
                raise ValueError('--write requires --reference-root')
            snapshot = read_reference(args.reference_root)
            args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
        else:
            snapshot = json.loads(args.snapshot.read_text())
            validate_snapshot(snapshot)
            if args.reference_root is not None and read_reference(args.reference_root) != snapshot:
                raise ValueError('Owning reference differs from frozen snapshot; regenerate and review the contract changes')
        errors = implementation_errors(snapshot['contract'])
        errors.extend(requirement_hook_errors(snapshot['contract'], Path(__file__).resolve().parents[1]))
        if errors:
            raise ValueError('\n'.join(errors))
    except (ValueError, KeyError, OSError) as error:
        print(f'Content conformance FAILED: {error}')
        return 1
    print('Content conformance passed: reference provenance, taxonomy, fallbacks and selected legacy mappings')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
