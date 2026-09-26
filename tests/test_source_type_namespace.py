"""One source namespace for domain installation and frontend lookup."""
import asyncio
import subprocess
import sys

import pytest

from culsma.domains.registry import SOURCE_TYPE_NAMES
from culsma.domains.observation import ObservationUnitBase, OBSERVATION_UNITS, STANDARD_OBSERVATION_UNITS
from culsma.domains.chromatography import (
    ChromatographyAxisBase, STANDARD_CHROMATOGRAPHY_REGISTRY, ACTIVE_CHROMATOGRAPHY_REGISTRY,
)
from culsma.pipeline.external_inputs import KNOWN_ENUM_TYPES


@pytest.mark.parametrize('name', sorted(set(SOURCE_TYPE_NAMES.builtins) | SOURCE_TYPE_NAMES.reserved))
@pytest.mark.parametrize('domain', ['observation', 'chromatography'])
def test_every_builtin_and_base_name_is_protected(name, domain):
    base, registry = (ObservationUnitBase, STANDARD_OBSERVATION_UNITS) if domain == 'observation' else (
        ChromatographyAxisBase, STANDARD_CHROMATOGRAPHY_REGISTRY)
    extension = base(name, {'CUSTOM': 'review_custom'})
    before = dict(SOURCE_TYPE_NAMES)
    with pytest.raises(ValueError):
        with registry.with_type(extension, 'review.collision').activate():
            pytest.fail('Reserved source namespace was installed')
    assert dict(SOURCE_TYPE_NAMES) == before


def test_nested_replacement_and_exception_restore_both_views():
    first = ObservationUnitBase('LabUnit', {'FIRST': 'first'})
    second = ObservationUnitBase('LabUnit', {'SECOND': 'second'})
    outer = STANDARD_OBSERVATION_UNITS.with_type(first, 'review.first')
    inner = STANDARD_OBSERVATION_UNITS.with_type(second, 'review.second')
    with outer.activate():
        assert KNOWN_ENUM_TYPES['LabUnit'] is first
        with pytest.raises(RuntimeError, match='body failure'):
            with inner.activate():
                assert KNOWN_ENUM_TYPES['LabUnit'] is second
                assert OBSERVATION_UNITS.current is inner
                raise RuntimeError('body failure')
        assert KNOWN_ENUM_TYPES['LabUnit'] is first
        assert OBSERVATION_UNITS.current is outer
        with STANDARD_OBSERVATION_UNITS.activate():
            assert 'LabUnit' not in KNOWN_ENUM_TYPES
        assert KNOWN_ENUM_TYPES['LabUnit'] is first
    assert 'LabUnit' not in KNOWN_ENUM_TYPES


def test_failed_cross_domain_activation_is_atomic():
    unit = ObservationUnitBase('SharedName', {'UNIT': 'unit'})
    axis = ChromatographyAxisBase('SharedName', {'AXIS': 'axis'})
    outer = STANDARD_OBSERVATION_UNITS.with_type(unit, 'review.unit')
    inner = STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(axis, 'review.axis')
    with outer.activate():
        with pytest.raises(ValueError, match='namespace collision'):
            with inner.activate():
                pytest.fail('Conflicting namespace installed')
        assert KNOWN_ENUM_TYPES['SharedName'] is unit
        assert OBSERVATION_UNITS.current is outer
        assert ACTIVE_CHROMATOGRAPHY_REGISTRY.get() is STANDARD_CHROMATOGRAPHY_REGISTRY


def test_parallel_contexts_have_independent_source_and_domain_views():
    first = ObservationUnitBase('ScopedUnit', {'FIRST': 'first'})
    second = ObservationUnitBase('ScopedUnit', {'SECOND': 'second'})

    async def check(family, identity):
        registry = STANDARD_OBSERVATION_UNITS.with_type(family, identity)
        with registry.activate():
            await asyncio.sleep(0)
            assert KNOWN_ENUM_TYPES['ScopedUnit'] is family
            assert OBSERVATION_UNITS.current is registry

    async def run_checks():
        await asyncio.gather(check(first, 'review.first'), check(second, 'review.second'))

    asyncio.run(run_checks())
    assert 'ScopedUnit' not in KNOWN_ENUM_TYPES


@pytest.mark.parametrize('first', [
    'culsma.domains.chromatography', 'culsma.domains.observation',
    'culsma.domains.constraints', 'culsma.domains.registry',
    'culsma.common.content_contracts',
])
def test_domain_import_smoke_is_independent_of_frontend_and_runtime(first):
    source = f'''
import {first}
import sys
from culsma.domains.observation import ObservationUnitBase, STANDARD_OBSERVATION_UNITS
from culsma.domains.registry import SOURCE_TYPE_NAMES
Collision = ObservationUnitBase('MagneticProgramOutput', {{'CUSTOM': 'custom'}})
try:
    with STANDARD_OBSERVATION_UNITS.with_type(Collision, 'smoke.collision').activate():
        raise AssertionError('collision accepted')
except ValueError:
    pass
assert SOURCE_TYPE_NAMES['MagneticProgramOutput'] is not Collision
assert not any(name.startswith(('culsma.pipeline', 'culsma.parser', 'culsma.runtime')) for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_frontend_uses_the_installation_namespace():
    assert KNOWN_ENUM_TYPES is SOURCE_TYPE_NAMES
