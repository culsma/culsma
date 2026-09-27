"""Verify the naming port can be replaced, not merely type-annotated."""
import ast
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from culsma.common.type_name_contracts import NamespaceBinding, TypeNamespace
from culsma.common.type_names import SourceTypeNamespace
from culsma.enum_services import SOURCE_TYPE_NAMES, ENUM_REGISTRATION_SOURCES
from culsma.domains.stream import ObservationUnitBase, OBSERVATION_UNITS
from culsma.domains.fractionation import (
    ChromatographyAxisBase, STANDARD_CHROMATOGRAPHY_REGISTRY,
)
from culsma.pipeline.external_inputs import ExternalInputResolver, ExternalInputScope, ExternalInputStatus
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember


class RecordingNamespace(Mapping):
    """Independent port adapter; deliberately does not inherit the implementation."""
    def __init__(self):
        self.delegate = SourceTypeNamespace()
        self.delegate.configure(SOURCE_TYPE_NAMES.builtins, SOURCE_TYPE_NAMES.reserved)
        self.calls = []

    def validate(self, owner, types):
        return self.delegate.validate(owner, types)

    @contextmanager
    def activate(self, owner, types):
        self.calls.append(('enter', owner))
        with self.delegate.activate(owner, types):
            try:
                yield self
            finally:
                self.calls.append(('exit', owner))

    def snapshot(self):
        return self.delegate.snapshot()

    def __getitem__(self, name):
        self.calls.append(('lookup', name))
        return self.delegate[name]

    def __iter__(self):
        return iter(self.delegate)

    def __len__(self):
        return len(self.delegate)


@pytest.mark.parametrize('domain', ['observation', 'chromatography'])
def test_registry_and_frontend_use_supplied_port(domain):
    service: TypeNamespace = RecordingNamespace()
    binding = NamespaceBinding(service)
    if domain == 'observation':
        contract = replace(OBSERVATION_UNITS, registry=replace(OBSERVATION_UNITS.registry, namespace=binding))
        family = ObservationUnitBase('InjectedUnit', {'CUSTOM': 'injected_unit'})
        registry = contract.standard_registry.with_type(family, 'test.unit')
        owner = registry.wire_domain
        assert registry.namespace is binding
    else:
        family = ChromatographyAxisBase('InjectedAxis', {'CUSTOM': 'injected_axis'})
        registry = replace(STANDARD_CHROMATOGRAPHY_REGISTRY, namespace=binding).with_type(family, 'test.axis')
        owner = 'chromatography'
        assert registry.namespace is binding
    with registry.activate():
        scope = ExternalInputScope(namespace=service)
        expression = IRMember(base=IRIdentifier(family.__name__), member='CUSTOM')
        result = ExternalInputResolver.resolve(expression, None, scope)
        assert result.status is ExternalInputStatus.RESOLVED
        assert result.value is family.CUSTOM
        assert family.__name__ not in SOURCE_TYPE_NAMES
    assert family.__name__ not in service
    assert ('enter', owner) in service.calls
    assert ('exit', owner) in service.calls
    assert ('lookup', family.__name__) in service.calls


def test_composition_injects_one_service_into_every_domain():
    assert STANDARD_CHROMATOGRAPHY_REGISTRY.namespace.require() is SOURCE_TYPE_NAMES
    assert all(current().namespace.require() is SOURCE_TYPE_NAMES for bases, current in ENUM_REGISTRATION_SOURCES)
    assert ExternalInputScope().namespace is SOURCE_TYPE_NAMES


def test_missing_dependency_fails_explicitly_and_binding_is_single_assignment():
    binding = NamespaceBinding()
    with pytest.raises(RuntimeError, match='must be bound'):
        binding.require()
    binding.bind(RecordingNamespace())
    with pytest.raises(RuntimeError, match='already bound'):
        binding.bind(RecordingNamespace())
    with pytest.raises(AttributeError):
        binding.service = RecordingNamespace()


@pytest.mark.parametrize('module', ['fractionation.py', 'stream.py', 'constraints.py', 'content.py', 'separation.py', 'data.py'])
def test_domains_depend_only_on_port_not_implementation_or_composition(module):
    root = Path(__file__).resolve().parents[1] / 'src/culsma/domains'
    tree = ast.parse((root / module).read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(name and name.startswith('culsma.common.') for name in imports)
    assert not any(name and name.split('.')[-1] in {'enum_services', 'type_names', 'registry'} for name in imports)
    assert not any(isinstance(node, ast.Name) and node.id == 'SOURCE_TYPE_NAMES' for node in ast.walk(tree))


@pytest.mark.parametrize('domain', ['observation', 'chromatography'])
def test_injected_service_failure_does_not_change_domain_state(domain):
    from culsma.domains.fractionation import ACTIVE_CHROMATOGRAPHY_REGISTRY

    class RejectingNamespace(RecordingNamespace):
        @contextmanager
        def activate(self, owner, types):
            raise ValueError('installation denied by injected service')
            yield  # context manager body never entered

    binding = NamespaceBinding(RejectingNamespace())
    if domain == 'observation':
        registry = replace(OBSERVATION_UNITS, registry=replace(OBSERVATION_UNITS.registry, namespace=binding)).standard_registry
        before = OBSERVATION_UNITS.current
    else:
        registry = replace(STANDARD_CHROMATOGRAPHY_REGISTRY, namespace=binding)
        before = ACTIVE_CHROMATOGRAPHY_REGISTRY.get()
    with pytest.raises(ValueError, match='installation denied'):
        with registry.activate():
            pytest.fail('Rejected service was ignored')
    after = OBSERVATION_UNITS.current if domain == 'observation' else ACTIVE_CHROMATOGRAPHY_REGISTRY.get()
    assert after == before
