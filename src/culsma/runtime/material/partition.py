"""Separation component partition strategies for material compute."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from culsma.pipeline.content_vocab import (
    ContentKind,
    ContentType,
    is_custom_content_type,
    is_standard_content_type,
    parse_content_kind,
    parse_content_type,
)
from culsma.runtime.material.support import _set_container_material


class PartitionClass(StrEnum):
    LIQUID_MATRIX = "liquid_matrix"
    PROCESS_LIQUID_MATRIX = "process_liquid_matrix"
    WASH_LIQUID = "wash_liquid"
    SOLUBLE_BIOSAMPLE_MATRIX = "soluble_biosample_matrix"
    LIQUID_REACTION_MATRIX = "liquid_reaction_matrix"
    PRECIPITATION_LIQUID = "precipitation_liquid"
    SOLUBLE_REAGENT = "soluble_reagent"
    SOLUBLE_COMPOUND = "soluble_compound"
    LIQUID_REAGENT = "liquid_reagent"
    STAIN_REAGENT = "stain_reagent"
    LIQUID_FRACTION = "liquid_fraction"
    PELLETABLE_CELLS = "pelletable_cells"
    PELLETABLE_MATERIAL = "pelletable_material"
    SOLID_SAMPLE = "solid_sample"
    SOLID_PARTICLE = "solid_particle"
    CAPTURE_PARTICLE = "capture_particle"
    RETAINED_FRACTION = "retained_fraction"
    MOLECULAR_TARGET = "molecular_target"
    COMPOSITE_SAMPLE = "composite_sample"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


def _parse_partition_class(value: str) -> PartitionClass:
    try:
        return PartitionClass(value)
    except ValueError:
        return PartitionClass.UNKNOWN


def _component_partition_ratios(container: dict[str, Any], component_id: str) -> tuple[float, float] | None:
    metadata = container.get("metadata")
    if not isinstance(metadata, dict):
        return None
    overrides = metadata.get("component_partition_ratios")
    if not isinstance(overrides, dict):
        return None
    raw = overrides.get(component_id)
    if isinstance(raw, dict):
        ratio0 = raw.get("0", raw.get(0))
        ratio1 = raw.get("1", raw.get(1))
    elif isinstance(raw, (list, tuple)) and len(raw) == 2:
        ratio0, ratio1 = raw
    else:
        return None
    try:
        ratio0_f = float(ratio0)
        ratio1_f = float(ratio1)
    except (TypeError, ValueError):
        return None
    total = ratio0_f + ratio1_f
    if ratio0_f < 0.0 or ratio1_f < 0.0 or total <= 0.0:
        return None
    return ratio0_f / total, ratio1_f / total


_LIQUID_PARTITION_CLASSES = {
    PartitionClass.LIQUID_MATRIX,
    PartitionClass.PROCESS_LIQUID_MATRIX,
    PartitionClass.WASH_LIQUID,
    PartitionClass.SOLUBLE_BIOSAMPLE_MATRIX,
    PartitionClass.LIQUID_REACTION_MATRIX,
    PartitionClass.PRECIPITATION_LIQUID,
    PartitionClass.SOLUBLE_REAGENT,
    PartitionClass.SOLUBLE_COMPOUND,
    PartitionClass.LIQUID_REAGENT,
    PartitionClass.STAIN_REAGENT,
    PartitionClass.LIQUID_FRACTION,
}
_PELLET_PARTITION_CLASSES = {
    PartitionClass.PELLETABLE_CELLS,
    PartitionClass.PELLETABLE_MATERIAL,
    PartitionClass.SOLID_SAMPLE,
    PartitionClass.SOLID_PARTICLE,
    PartitionClass.CAPTURE_PARTICLE,
    PartitionClass.RETAINED_FRACTION,
}
_TARGET_PARTITION_CLASSES = {PartitionClass.MOLECULAR_TARGET}

_CONTENT_CLASS_BY_KIND_TYPE: dict[tuple[ContentKind, ContentType], PartitionClass] = {
    **{
        (ContentKind.BIOSAMPLE, content_type): PartitionClass.LIQUID_MATRIX
        for content_type in (ContentType.PLASMA, ContentType.SERUM, ContentType.SOLUTION)
    },
    **{
        (ContentKind.BIOSAMPLE, content_type): PartitionClass.PELLETABLE_CELLS
        for content_type in (ContentType.CELL_SUSPENSION, ContentType.MIXED_CELLS, ContentType.ADHERENT_CELLS)
    },
    (ContentKind.BIOSAMPLE, ContentType.CELL_PELLET): PartitionClass.PELLETABLE_MATERIAL,
    **{
        (ContentKind.BIOSAMPLE, content_type): PartitionClass.SOLUBLE_BIOSAMPLE_MATRIX
        for content_type in (ContentType.CELL_LYSATE, ContentType.EXTRACT, ContentType.MOLECULAR_EXTRACT)
    },
    **{
        (ContentKind.BIOSAMPLE, content_type): PartitionClass.MOLECULAR_TARGET
        for content_type in (
            ContentType.DNA_SAMPLE,
            ContentType.SAMPLE_DNA,
            ContentType.DNA_SOLUTION,
            ContentType.DNA_LYSATE,
            ContentType.DNA_STOCK,
            ContentType.PURIFIED_DNA,
            ContentType.TEMPLATE_DNA,
            ContentType.AMPLICON,
            ContentType.PLASMID_VECTOR,
            ContentType.DNA_INSERT,
        )
    },
    (ContentKind.BIOSAMPLE, ContentType.REACTION_MIX): PartitionClass.LIQUID_REACTION_MATRIX,
    (ContentKind.BIOSAMPLE, ContentType.TISSUE_PIECE): PartitionClass.SOLID_SAMPLE,
    (ContentKind.BIOSAMPLE, ContentType.WHOLE_BLOOD): PartitionClass.COMPOSITE_SAMPLE,
    (ContentKind.BIOSAMPLE, ContentType.CELL_OR_TISSUE_SAMPLE): PartitionClass.COMPOSITE_SAMPLE,
    **{
        (ContentKind.BUFFER, content_type): PartitionClass.LIQUID_MATRIX
        for content_type in (
            ContentType.BUFFER,
            ContentType.WATER,
            ContentType.DILUENT,
            ContentType.TE_BUFFER,
            ContentType.ELUTION_BUFFER,
            ContentType.RESUSPENSION_BUFFER,
            ContentType.PHOSPHATE_BUFFER,
            ContentType.REACTION_BUFFER,
            ContentType.CULTURE_MEDIA,
            ContentType.CULTURE_MEDIUM,
            ContentType.REACTION_MEDIA,
            ContentType.MEDIA,
            ContentType.DRUG_STOCK,
            ContentType.SEQUENCING_READ_BUFFER,
            ContentType.TEST_BUFFER,
        )
    },
    **{
        (ContentKind.BUFFER, content_type): PartitionClass.PROCESS_LIQUID_MATRIX
        for content_type in (
            ContentType.LYSIS_BUFFER,
            ContentType.BINDING_BUFFER,
            ContentType.NUCLEIC_ACID_EXTRACTION_BUFFER,
            ContentType.MOLECULAR_EXTRACTION_BUFFER,
        )
    },
    **{
        (ContentKind.BUFFER, content_type): PartitionClass.WASH_LIQUID
        for content_type in (
            ContentType.WASH_BUFFER,
            ContentType.ETHANOL_WASH_BUFFER,
            ContentType.COLUMN_WASH_BUFFER,
            ContentType.COLUMN_WASH_BUFFER_1,
            ContentType.COLUMN_WASH_BUFFER_2,
        )
    },
    (ContentKind.REAGENT, ContentType.PRECIPITATION_REAGENT): PartitionClass.PRECIPITATION_LIQUID,
    (ContentKind.REAGENT, ContentType.MAGNETIC_BEAD): PartitionClass.CAPTURE_PARTICLE,
    (ContentKind.REAGENT, ContentType.AGAROSE_POWDER): PartitionClass.SOLID_PARTICLE,
    (ContentKind.REAGENT, ContentType.POWDER): PartitionClass.SOLID_PARTICLE,
    **{
        (ContentKind.REAGENT, content_type): PartitionClass.SOLUBLE_REAGENT
        for content_type in (ContentType.TAQ_POLYMERASE, ContentType.ENZYME, ContentType.FLUOR_ANTIBODY)
    },
    **{
        (ContentKind.REAGENT, content_type): PartitionClass.SOLUBLE_COMPOUND
        for content_type in (
            ContentType.FEED,
            ContentType.NUTRIENT_FEED,
            ContentType.VEHICLE_CONTROL,
            ContentType.POSITIVE_CONTROL_COMPOUND,
            ContentType.COMPOUND_X_LOW,
            ContentType.COMPOUND_X_MID,
            ContentType.COMPOUND_X_HIGH,
            ContentType.COMPOUND_X_MAX,
            ContentType.DRUG_X,
            ContentType.COMPOUND_X_STOCK,
        )
    },
    **{
        (ContentKind.REAGENT, content_type): PartitionClass.LIQUID_REAGENT
        for content_type in (
            ContentType.QPCR_MASTER_MIX,
            ContentType.STANDARD_MIX,
            ContentType.FLUOR_QUANT_MIX,
            ContentType.FRAGMENTATION_REAGENT,
            ContentType.ADAPTER_MIX,
            ContentType.LIGATION_REAGENT,
            ContentType.CLEANUP_REAGENT,
            ContentType.AMPLIFICATION_REAGENT,
            ContentType.IONIZATION_REAGENT,
            ContentType.ANTICOAGULANT,
        )
    },
    (ContentKind.REAGENT, ContentType.DNA_STAIN): PartitionClass.STAIN_REAGENT,
    (ContentKind.REAGENT, ContentType.PLATE_STAIN): PartitionClass.STAIN_REAGENT,
    (ContentKind.FRACTION, ContentType.SUPERNATANT): PartitionClass.LIQUID_FRACTION,
    (ContentKind.FRACTION, ContentType.FILTRATE): PartitionClass.LIQUID_FRACTION,
    (ContentKind.FRACTION, ContentType.TARGET_PHASE): PartitionClass.LIQUID_FRACTION,
    (ContentKind.FRACTION, ContentType.PELLET): PartitionClass.RETAINED_FRACTION,
    (ContentKind.FRACTION, ContentType.PRECIPITATE): PartitionClass.RETAINED_FRACTION,
    (ContentKind.FRACTION, ContentType.WASHED_DNA_PELLET): PartitionClass.RETAINED_FRACTION,
    (ContentKind.FRACTION, ContentType.RETENTATE): PartitionClass.RETAINED_FRACTION,
}


def partition_sep_material(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    program_kind: str,
) -> dict[str, Any]:
    source_components = source.setdefault("components", {})
    if not isinstance(source_components, dict) or not source_components:
        ratio0, ratio1 = 0.5, 0.5
        source_volume = float(source.get("volume_uL", 0.0))
        source_mass = float(source.get("mass_mg", 0.0))
        _set_container_material(slot0, volume_uL=source_volume * ratio0, mass_mg=source_mass * ratio0, components={})
        _set_container_material(slot1, volume_uL=source_volume * ratio1, mass_mg=source_mass * ratio1, components={})
        if source is not slot0 and source is not slot1:
            _set_container_material(source, volume_uL=0.0, mass_mg=0.0, components={})
        return {"mode": "generic_empty", "default_ratio": ratio0}

    strategy = SepPartitionStrategyRegistry().strategy_for(program_kind)
    class_resolver = ContentClassResolver()
    slot0_components: dict[str, float] = {}
    slot1_components: dict[str, float] = {}
    slot0_classes: dict[str, str] = {}
    slot1_classes: dict[str, str] = {}
    class_counts: dict[str, int] = {}
    ratios_by_class: dict[str, tuple[float, float]] = {}
    ratios_by_component: dict[str, tuple[float, float]] = {}

    for name, amount in list(source_components.items()):
        amount_f = float(amount)
        partition_class = class_resolver.classify(state, source, str(name))
        ratio0, ratio1 = _component_partition_ratios(source, str(name)) or strategy.ratios(partition_class)
        class_key = partition_class.value
        class_counts[class_key] = class_counts.get(class_key, 0) + 1
        ratios_by_class[class_key] = (ratio0, ratio1)
        ratios_by_component[str(name)] = (ratio0, ratio1)
        slot0_components[str(name)] = slot0_components.get(str(name), 0.0) + amount_f * ratio0
        slot1_components[str(name)] = slot1_components.get(str(name), 0.0) + amount_f * ratio1
        slot0_classes[str(name)] = strategy.output_class(partition_class, slot="0").value
        slot1_classes[str(name)] = strategy.output_class(partition_class, slot="1").value

    source_volume = float(source.get("volume_uL", 0.0))
    source_mass = float(source.get("mass_mg", 0.0))
    _set_container_material(
        slot0,
        volume_uL=source_volume * 0.5,
        mass_mg=source_mass * 0.5,
        components=slot0_components,
        component_classes=slot0_classes,
    )
    _set_container_material(
        slot1,
        volume_uL=source_volume * 0.5,
        mass_mg=source_mass * 0.5,
        components=slot1_components,
        component_classes=slot1_classes,
    )
    if source is not slot0 and source is not slot1:
        _set_container_material(source, volume_uL=0.0, mass_mg=0.0, components={})

    return {
        "mode": "program_partition",
        "strategy": strategy.program_kind,
        "slot_contract": dict(strategy.slot_contract),
        "classes": class_counts,
        "ratios_by_class": {name: {"0": ratios[0], "1": ratios[1]} for name, ratios in ratios_by_class.items()},
        "ratios_by_component": {name: {"0": ratios[0], "1": ratios[1]} for name, ratios in ratios_by_component.items()},
    }


class ContentClassResolver:
    def classify(self, state: dict[str, Any], container: dict[str, Any], component_id: str) -> PartitionClass:
        metadata = container.get("metadata")
        if isinstance(metadata, dict):
            overrides = metadata.get("component_partition_classes")
            if isinstance(overrides, dict):
                override = overrides.get(component_id)
                if isinstance(override, str) and override:
                    return _parse_partition_class(override)
        registry = state.get("content_registry")
        meta = registry.get(component_id) if isinstance(registry, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        kind_value = str(meta.get("content_kind", "") or "").lower()
        type_value = str(meta.get("content_type", "") or "").lower()
        if is_custom_content_type(type_value):
            kind = parse_content_kind(kind_value)
            if kind == ContentKind.BUFFER:
                return PartitionClass.PROCESS_LIQUID_MATRIX
            if kind == ContentKind.REAGENT:
                return PartitionClass.LIQUID_REAGENT
            return PartitionClass.CUSTOM
        if not is_standard_content_type(kind_value, type_value):
            return PartitionClass.UNKNOWN
        kind = parse_content_kind(kind_value)
        content_type = parse_content_type(type_value)
        if kind is None or content_type is None:
            return PartitionClass.UNKNOWN
        mapped = _CONTENT_CLASS_BY_KIND_TYPE.get((kind, content_type))
        if mapped is not None:
            return mapped
        return PartitionClass.UNKNOWN


class SepPartitionStrategy:
    program_kind = "sep_program"
    slot_contract: dict[str, str] = {"0": "fraction_0", "1": "fraction_1"}

    def ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in {PartitionClass.CUSTOM, PartitionClass.UNKNOWN, PartitionClass.COMPOSITE_SAMPLE}:
            return (0.5, 0.5)
        return self._known_ratios(partition_class)

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        return (0.5, 0.5)

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        return partition_class


class CentrifugePartitionStrategy(SepPartitionStrategy):
    program_kind = "centrifuge_program"
    slot_contract = {"0": "supernatant", "1": "pellet"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _PELLET_PARTITION_CLASSES:
            return (0.01, 0.99)
        return (0.99, 0.01)


class PhasePartitionStrategy(SepPartitionStrategy):
    program_kind = "phase_partition_program"
    slot_contract = {"0": "target_phase", "1": "other_phase"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES or partition_class in {
            PartitionClass.LIQUID_MATRIX,
            PartitionClass.PROCESS_LIQUID_MATRIX,
            PartitionClass.SOLUBLE_BIOSAMPLE_MATRIX,
            PartitionClass.LIQUID_REACTION_MATRIX,
            PartitionClass.LIQUID_FRACTION,
        }:
            return (0.98, 0.02)
        if partition_class in {
            PartitionClass.LIQUID_REAGENT,
            PartitionClass.PRECIPITATION_LIQUID,
            PartitionClass.STAIN_REAGENT,
            PartitionClass.WASH_LIQUID,
        }:
            return (0.02, 0.98)
        return (0.1, 0.9)


class PrecipitationPartitionStrategy(SepPartitionStrategy):
    program_kind = "precipitation_program"
    slot_contract = {"0": "precipitate", "1": "supernatant"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES or partition_class in _PELLET_PARTITION_CLASSES:
            return (0.95, 0.05)
        if partition_class in _LIQUID_PARTITION_CLASSES:
            return (0.03, 0.97)
        return (0.5, 0.5)

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "0" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class


class FiltrationPartitionStrategy(SepPartitionStrategy):
    program_kind = "filtration_program"
    slot_contract = {"0": "filtrate", "1": "retentate"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES or partition_class in _PELLET_PARTITION_CLASSES:
            return (0.02, 0.98)
        return (0.98, 0.02)

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "1" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class


class MagneticPartitionStrategy(SepPartitionStrategy):
    program_kind = "magnetic_program"
    slot_contract = {"0": "bound", "1": "flowthrough"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class == PartitionClass.CAPTURE_PARTICLE
            or partition_class == PartitionClass.RETAINED_FRACTION
        ):
            return (0.98, 0.02)
        return (0.02, 0.98)

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "0" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class == PartitionClass.CAPTURE_PARTICLE
            or partition_class == PartitionClass.RETAINED_FRACTION
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class


class DisruptPartitionStrategy(SepPartitionStrategy):
    program_kind = "disrupt_program"
    slot_contract = {"0": "lysate", "1": "debris_or_residue"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _PELLET_PARTITION_CLASSES:
            return (0.05, 0.95)
        return (0.95, 0.05)


class FieldPartitionStrategy(SepPartitionStrategy):
    program_kind = "field_program"
    slot_contract = {"0": "target_band_fraction", "1": "non_target_fraction"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES:
            return (0.95, 0.05)
        return (0.05, 0.95)


_DEFAULT_SEP_PARTITION_STRATEGY = SepPartitionStrategy()
_SEP_PARTITION_STRATEGIES: dict[str, SepPartitionStrategy] = {
    strategy.program_kind: strategy
    for strategy in (
        CentrifugePartitionStrategy(),
        PhasePartitionStrategy(),
        PrecipitationPartitionStrategy(),
        FiltrationPartitionStrategy(),
        MagneticPartitionStrategy(),
        DisruptPartitionStrategy(),
        FieldPartitionStrategy(),
    )
}


class SepPartitionStrategyRegistry:
    def __init__(self, strategies: dict[str, SepPartitionStrategy] | None = None) -> None:
        self.strategies = strategies or _SEP_PARTITION_STRATEGIES

    def strategy_for(self, program_kind: str) -> SepPartitionStrategy:
        return self.strategies.get(program_kind, _DEFAULT_SEP_PARTITION_STRATEGY)


def _sep_partition_strategy(program_kind: str) -> SepPartitionStrategy:
    return SepPartitionStrategyRegistry().strategy_for(program_kind)
