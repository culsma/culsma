"""Architectural boundaries and persisted identities survive syntax ownership changes."""
import ast
from pathlib import Path
import subprocess
import sys

import pytest

from culsma.common import content_contracts
from culsma.domains import content, stream
from culsma.enum_services import PARAMETER_ENUM_TYPES


def test_content_reuses_common_classification():
    assert content.ContentClassification is content_contracts.ContentClassification
    assert content.CONTENT_CONTRACT.fields['kind'].enum_type is content_contracts.ContentKind
    assert content.CONTENT_CONTRACT.fields['type'].enum_type is content_contracts.ContentType
    assert content.CONTENT_CONTRACT.fields['attrs'] is content.CONTENT_ATTRIBUTES


@pytest.mark.parametrize('module', ['content', 'stream', 'constraints', 'fractionation', 'separation', 'data', 'groups'])
def test_domain_import_does_not_assemble_application(module):
    script = f'''
import sys
import culsma.domains.{module}
assert 'culsma.enum_services' not in sys.modules
assert not any(name.startswith(('culsma.pipeline', 'culsma.runtime', 'culsma.parser')) for name in sys.modules)
import culsma.enum_services
assert culsma.enum_services.SOURCE_TYPE_NAMES['ObservationUnit'].__name__ == 'ObservationUnit'
'''
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize('domain,member,expected', [
    ('observation_unit', 'SINGLE_CELL', stream.ObservationUnit.SINGLE_CELL),
    ('content_role', 'CULTURE', content.ContentRole.CULTURE),
    ('content_state', 'SUSPENSION', content.ContentState.SUSPENSION),
    ('bead_property', 'MAGNETIC', content.BeadProperty.MAGNETIC),
])
def test_previous_wire_payloads_decode_without_python_paths(domain, member, expected):
    payload = {'kind': 'DomainEnum', 'domain': domain, 'id': f'culsma.{domain}',
               'version': 1, 'member': member}
    assert PARAMETER_ENUM_TYPES.decode_registered(payload) is expected


def test_common_tools_do_not_depend_on_language_modules():
    root = Path(__file__).resolve().parents[1] / 'src/culsma/common'
    for name in ('enum_parameters', 'enum_registration', 'enum_type_table', 'type_names', 'type_name_contracts'):
        tree = ast.parse((root / f'{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith(('culsma.domains', 'culsma.enum_services', 'culsma.pipeline', 'culsma.runtime'))
            elif isinstance(node, ast.Import):
                assert not any(item.name.startswith(('culsma.domains', 'culsma.enum_services', 'culsma.pipeline', 'culsma.runtime')) for item in node.names)
