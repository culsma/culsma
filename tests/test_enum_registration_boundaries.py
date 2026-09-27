"""A registered enum has one parameter family and one scoped wire identity."""
from dataclasses import replace
import pytest

from culsma.common.enum_registration import EnumTypeRegistration
from culsma.domains.data import DataKindBase, DataKind, STANDARD_DATA_KINDS
from culsma.domains.separation import FiltrationDriveBase, STANDARD_FILTRATION_DRIVES
from culsma.domains.fractionation import (
    ChromatographyAxisBase, ChromatographyOrderBase, ChromatographyAxis,
    ChromatographyType, ChromatographyRegistry, STANDARD_CHROMATOGRAPHY_REGISTRY,
)
from culsma.pipeline.external_boundary import ExternalEnumCodec
from culsma.enum_services import SOURCE_TYPE_NAMES


class MixedDataDrive(DataKindBase, FiltrationDriveBase):
    VALUE = 'mixed_data_drive'


class MixedDriveData(FiltrationDriveBase, DataKindBase):
    VALUE = 'mixed_drive_data'


class MixedDataAxis(DataKindBase, ChromatographyAxisBase):
    VALUE = 'mixed_data_axis'


class MixedAxisOrder(ChromatographyOrderBase, ChromatographyAxisBase):
    VALUE = ('mixed_axis_order', ChromatographyAxis.RETENTION_TIME)


@pytest.mark.parametrize('family,registry', [
    (MixedDataDrive, STANDARD_DATA_KINDS),
    (MixedDataDrive, STANDARD_FILTRATION_DRIVES),
    (MixedDriveData, STANDARD_DATA_KINDS),
    (MixedDriveData, STANDARD_FILTRATION_DRIVES),
    (MixedDataAxis, STANDARD_DATA_KINDS),
    (MixedDataAxis, STANDARD_CHROMATOGRAPHY_REGISTRY),
    (MixedAxisOrder, STANDARD_CHROMATOGRAPHY_REGISTRY),
])
@pytest.mark.parametrize('constructor', [False, True])
def test_mixed_family_is_rejected_at_registration(family, registry, constructor):
    with pytest.raises(TypeError, match='one enum family'):
        if not constructor:
            registry.with_type(family, 'example.mixed')
        elif isinstance(registry, ChromatographyRegistry):
            replace(registry, entries=(*registry.entries, ChromatographyType(family, 'example.mixed', 1)))
        else:
            replace(registry, entries=(*registry.entries, EnumTypeRegistration(family, 'example.mixed')))
    assert family.__name__ not in SOURCE_TYPE_NAMES


def test_one_family_can_use_intermediate_bases_and_plain_mixins():
    class Intermediate(DataKindBase):
        pass

    class DisplayMixin:
        def display(self):
            return self.value.upper()

    class LocalKind(DisplayMixin, Intermediate):
        CUSTOM = 'custom_kind'

    registry = STANDARD_DATA_KINDS.with_type(LocalKind, 'example.custom')
    with registry.activate():
        codec = ExternalEnumCodec()
        assert codec.decode(codec.encode(LocalKind.CUSTOM)) is LocalKind.CUSTOM
        assert LocalKind.CUSTOM.display() == 'CUSTOM_KIND'


class ScopedDataKind(DataKindBase):
    CUSTOM = 'scoped_kind'


class ScopedAxis(ChromatographyAxisBase):
    CUSTOM = 'scoped_axis'


@pytest.mark.parametrize('family,registry', [
    (ScopedDataKind, STANDARD_DATA_KINDS),
    (ScopedAxis, STANDARD_CHROMATOGRAPHY_REGISTRY),
])
def test_open_types_cannot_use_closed_payload_even_from_cached_codec(family, registry):
    member = family.CUSTOM
    closed_payload = {'kind': 'ExternalEnum', 'enum': family.__name__, 'member': 'CUSTOM'}
    with registry.with_type(family, 'example.scoped').activate():
        codec = ExternalEnumCodec()
        explicit_codec = ExternalEnumCodec({family.__name__: family})
        payload = codec.encode(member)
        assert codec.decode(payload) is member
        for instance in (codec, explicit_codec):
            with pytest.raises(ValueError):
                instance.decode(closed_payload)
    for instance in (codec, explicit_codec):
        with pytest.raises(ValueError):
            instance.decode(closed_payload)
        with pytest.raises(ValueError):
            instance.decode(payload)


def test_standard_open_type_also_requires_its_identity_payload():
    codec = ExternalEnumCodec()
    assert codec.decode(codec.encode(DataKind.OBSERVATION)) is DataKind.OBSERVATION
    with pytest.raises(ValueError):
        codec.decode({'kind': 'ExternalEnum', 'enum': 'DataKind', 'member': 'OBSERVATION'})


def test_retained_codec_checks_current_registry_version_in_nested_scopes():
    first = STANDARD_DATA_KINDS.with_type(ScopedDataKind, 'example.scoped', version=1)
    second = STANDARD_DATA_KINDS.with_type(ScopedDataKind, 'example.scoped', version=2)
    with first.activate():
        codec = ExternalEnumCodec()
        payload = codec.encode(ScopedDataKind.CUSTOM)
        with second.activate():
            with pytest.raises(ValueError):
                codec.decode(payload)
            current = codec.encode(ScopedDataKind.CUSTOM)
            assert current['version'] == 2
            assert codec.decode(current) is ScopedDataKind.CUSTOM
        assert codec.decode(payload) is ScopedDataKind.CUSTOM
    with pytest.raises(ValueError):
        codec.decode(payload)
