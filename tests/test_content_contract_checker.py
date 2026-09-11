"""The checker must fail for spec drift, not merely accept the current fixture."""

from copy import deepcopy
import json

import pytest

from conformance.content_contract import (
    SNAPSHOT, SECTIONS, TEST_HOOKS, extract_section, implementation_errors, main,
    project_contract, read_reference, snapshot_from_sections, table_rows, validate_snapshot,
)

SNAPSHOT_DATA = json.loads(SNAPSHOT.read_text())


def source_sections():
    return {key:value['markdown'] for key,value in SNAPSHOT_DATA['sources'].items()}


def materialize_reference(root):
    files = {}
    for key, (file, heading) in SECTIONS.items():
        files.setdefault(file,[]).append(SNAPSHOT_DATA['sources'][key]['markdown'])
    for file, sections in files.items():
        (root/file).write_text('\n'.join(sections))


@pytest.mark.parametrize('mutation', ['missing','extra','wrong_pair','wrong_fallback','legacy_metadata'])
def test_detects_implementation_contract_drift(mutation):
    contract = deepcopy(SNAPSHOT_DATA['contract'])
    if mutation == 'missing':
        contract['types_by_kind']['formulation'].remove('medium')
    elif mutation == 'extra':
        contract['types_by_kind']['formulation'].append('invented_type')
    elif mutation == 'wrong_pair':
        contract['types_by_kind']['formulation'].remove('medium')
        contract['types_by_kind']['chemical'].append('medium')
    elif mutation == 'wrong_fallback':
        contract['fallback_by_kind']['formulation'] = 'other_chemical'
    else:
        contract['legacy_cases'][0]['attrs'] = {'state':'wrong'}
    assert implementation_errors(contract)


def test_snapshot_cannot_be_independently_edited():
    snapshot = deepcopy(SNAPSHOT_DATA)
    snapshot['contract']['roles_open'] = False
    with pytest.raises(ValueError,match='Snapshot differs'):
        validate_snapshot(snapshot)
    snapshot = deepcopy(SNAPSHOT_DATA)
    snapshot['sources']['types']['sha256'] = 'tampered'
    with pytest.raises(ValueError,match='Snapshot differs'):
        validate_snapshot(snapshot)


@pytest.mark.parametrize('mutation', ['duplicate_type','missing_fallback','closed_roles','missing_diagnostic'])
def test_extractor_rejects_ambiguous_or_incomplete_reference(mutation):
    sections=source_sections()
    if mutation == 'duplicate_type':
        sections['types']=sections['types'].replace('| `formulation` | `medium` |','| `formulation` | `medium`, `medium` |')
    elif mutation == 'missing_fallback':
        sections['types']=sections['types'].replace('`other_formulation`','`lab_unknown`')
    elif mutation == 'closed_roles':
        sections['types']=sections['types'].replace('Non-standard `attrs.role` values MAY be recorded as ordinary attr metadata','Unknown roles MUST be rejected')
    else:
        sections['diagnostics']=sections['diagnostics'].replace('`MAT_CONTENT_CLASSIFICATION_INVALID`','`RENAMED_CODE`')
    with pytest.raises(ValueError):
        project_contract(sections)


def test_cli_checks_real_reference_and_returns_failure_on_drift(tmp_path):
    materialize_reference(tmp_path)
    assert read_reference(tmp_path) == SNAPSHOT_DATA
    assert main(['--reference-root',str(tmp_path),'--check']) == 0
    target=tmp_path/'snapshot.json'
    assert main(['--reference-root',str(tmp_path),'--snapshot',str(target),'--write']) == 0
    assert json.loads(target.read_text()) == SNAPSHOT_DATA
    assert main(['--snapshot',str(target),'--check']) == 0
    file=tmp_path/SECTIONS['types'][0]
    file.write_text(file.read_text().replace('`medium` | `culture`','`medium` | `new_recommendation`'))
    assert main(['--reference-root',str(tmp_path),'--check']) == 1


def test_cli_missing_inputs_fail(tmp_path):
    assert main(['--write']) == 1
    assert main(['--snapshot',str(tmp_path/'absent.json'),'--check']) == 1


def test_section_and_table_parser_fail_closed():
    with pytest.raises(ValueError):
        extract_section('## A\n## A\n','## A')
    assert extract_section('## A\nbody\n### Child\nchild\n## B\n','## A') == '## A\nbody\n### Child\nchild\n'
    with pytest.raises(ValueError):
        table_rows('| A | B |\n|---|---|\n| only |\n','A')
    with pytest.raises(ValueError):
        table_rows('no table','A')


def test_requirement_hooks_are_executable_and_missing_hooks_fail():
    from pathlib import Path
    from conformance.content_contract import requirement_hook_errors
    root=Path(__file__).resolve().parents[1]
    contract=deepcopy(SNAPSHOT_DATA['contract'])
    assert requirement_hook_errors(contract,root) == []
    hooks=json.loads(TEST_HOOKS.read_text())
    hooks['CNT-ENUM-01']=['tests/test_content_reference_conformance.py::test_missing']
    assert requirement_hook_errors(contract,root,hooks)
    hooks['CNT-ENUM-01']=['tests/absent.py']
    assert requirement_hook_errors(contract,root,hooks)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'empty', 'malformed'])
def test_independent_evidence_mapping_rejects_invalid_hooks(mutation):
    from pathlib import Path
    from conformance.content_contract import requirement_hook_errors
    hooks=json.loads(TEST_HOOKS.read_text())
    if mutation == 'missing':
        del hooks['CNT-ENUM-01']
    elif mutation == 'extra':
        hooks['CNT-ENUM-08']=hooks['CNT-ENUM-01']
    elif mutation == 'empty':
        hooks['CNT-ENUM-01']=[]
    else:
        hooks['CNT-ENUM-01']=['../../external.py']
    assert requirement_hook_errors(SNAPSHOT_DATA['contract'],Path(__file__).resolve().parents[1],hooks)


def test_reference_requirements_are_readable_without_test_paths():
    sections=source_sections()
    assert 'tests/' not in sections['mapping']
    assert 'Span' not in sections['mapping']
    assert 'implementation baseline' not in sections['mapping']
    requirements=project_contract(sections)['requirements']
    assert all(entry['owner'] and entry['coverage'] for entry in requirements.values())
    assert all('test' not in entry for entry in requirements.values())
