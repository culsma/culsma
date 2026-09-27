import json
from enum import StrEnum
import pytest
from culsma.domains.fractionation import (
    ChromatographyAxisBase, ChromatographyOrderBase, ChromatographyAxis, ChromatographyOrder,
    STANDARD_CHROMATOGRAPHY_REGISTRY, ACTIVE_CHROMATOGRAPHY_REGISTRY,
)
from culsma.pipeline.external_boundary import ExternalEnumCodec


class LabAxis(ChromatographyAxisBase):
    ELUTION_VOLUME = 'elution_volume'


class LabOrder(ChromatographyOrderBase):
    SMALL_TO_LARGE = ('small_to_large', LabAxis.ELUTION_VOLUME)


def installed_registry():
    return (STANDARD_CHROMATOGRAPHY_REGISTRY
            .with_type(LabAxis, 'example.chromatography.axis')
            .with_type(LabOrder, 'example.chromatography.order'))


def test_scoped_registry_and_stable_json_identity():
    registry = installed_registry()
    before = ACTIVE_CHROMATOGRAPHY_REGISTRY.get()
    with registry.activate():
        codec = ExternalEnumCodec()
        payload = json.loads(json.dumps(codec.encode(LabAxis.ELUTION_VOLUME)))
        assert payload == {'kind': 'ChromatographyEnum', 'family': 'axis',
                           'id': 'example.chromatography.axis', 'version': 1, 'member': 'ELUTION_VOLUME'}
        assert codec.decode(payload) is LabAxis.ELUTION_VOLUME
        with before.activate():
            with pytest.raises(ValueError, match='Unknown'):
                codec.decode(payload)
        assert codec.decode(payload) is LabAxis.ELUTION_VOLUME
    assert ACTIVE_CHROMATOGRAPHY_REGISTRY.get() is before


def test_decode_uses_identity_not_python_class_name():
    class RenamedAxis(ChromatographyAxisBase):
        ELUTION_VOLUME = 'elution_volume'
    payload = installed_registry().encode(LabAxis.ELUTION_VOLUME)
    renamed = STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(RenamedAxis, 'example.chromatography.axis')
    assert renamed.decode(payload) is RenamedAxis.ELUTION_VOLUME


@pytest.mark.parametrize('field,value', [('version', 2), ('version', True), ('family', 'order'),
                                        ('member', 'UNKNOWN'), ('id', 'unknown')])
def test_wire_identity_rejects_unknowns(field, value):
    registry = installed_registry()
    payload = registry.encode(LabAxis.ELUTION_VOLUME)
    payload[field] = value
    with pytest.raises(ValueError):
        registry.decode(payload)


def test_registration_rejects_duplicates_collisions_and_foreign_types():
    registry = installed_registry()
    with pytest.raises(ValueError):
        registry.with_type(LabAxis, 'other.id')
    with pytest.raises(ValueError):
        STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(LabAxis, 'culsma.chromatography.axis')
    with pytest.raises(ValueError):
        STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(LabOrder, 'lab.order')
    class BadAxis(ChromatographyAxisBase):
        COLLISION = 'retention_time'
    with pytest.raises(ValueError):
        registry.with_type(BadAxis, 'bad.axis')
    class Wrong(StrEnum):
        X = 'x'
    with pytest.raises(TypeError):
        registry.with_type(Wrong, 'wrong.axis')
    assert 'LabAxis' not in STANDARD_CHROMATOGRAPHY_REGISTRY.types


def test_axis_and_order_require_exact_pair():
    registry = installed_registry()
    registry.validate_pair(LabAxis.ELUTION_VOLUME, LabOrder.SMALL_TO_LARGE)
    for axis, order in [(LabAxis.ELUTION_VOLUME, ChromatographyOrder.EARLY_TO_LATE),
                        (ChromatographyAxis.RETENTION_TIME, LabOrder.SMALL_TO_LARGE),
                        ('elution_volume', LabOrder.SMALL_TO_LARGE)]:
        with pytest.raises(ValueError):
            registry.validate_pair(axis, order)


def test_registry_constructor_and_activation_cannot_bypass_contract():
    from culsma.domains.fractionation import ChromatographyRegistry, ChromatographyType
    with pytest.raises(ValueError):
        ChromatographyRegistry((ChromatographyType(LabAxis, 'culsma.chromatography.axis', 1),))
    with pytest.raises(ValueError):
        with ChromatographyRegistry().activate():
            pass
    with pytest.raises(ValueError):
        STANDARD_CHROMATOGRAPHY_REGISTRY.with_type(LabAxis, 'lab.axis', version=True)
    with pytest.raises(ValueError):
        ChromatographyRegistry((ChromatographyType(ChromatographyAxis, 'changed.standard', 1),))
