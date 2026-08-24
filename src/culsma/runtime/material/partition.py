"""Separation component partition strategies for material compute."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from culsma.pipeline.content_vocab import (
    ContentKind,
    ContentType,
    is_standard_content_type,
    normalize_content_classification,
    parse_content_kind,
    parse_content_type,
)
from culsma.runtime.material.ledger import set_container_material
from culsma.runtime.material.separation_fate import (
    ExplicitContentFate,
    resolve_content_fate,
    resolve_content_physical_state,
    resolve_separation_operation_contract,
)


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
_EQUAL_SPLIT = (0.5, 0.5)
_NEAR_COMPLETE_TO_SLOT0 = (0.99, 0.01)
_NEAR_COMPLETE_TO_SLOT1 = (0.01, 0.99)
_TARGETED_RECOVERY_TO_SLOT0 = (0.95, 0.05)
_TARGETED_RECOVERY_TO_SLOT1 = (0.05, 0.95)

_CONTENT_CLASS_BY_KIND_TYPE: dict[tuple[ContentKind, ContentType], PartitionClass] = {
    (ContentKind.BIO_FLUID, ContentType.WHOLE_BLOOD): PartitionClass.COMPOSITE_SAMPLE,
    **{
        (ContentKind.BIO_FLUID, content_type): PartitionClass.LIQUID_MATRIX
        for content_type in (
            ContentType.PLASMA,
            ContentType.SERUM,
            ContentType.URINE,
            ContentType.SALIVA,
            ContentType.LYMPH,
            ContentType.CEREBROSPINAL_FLUID,
            ContentType.TEARS,
            ContentType.SEMEN,
            ContentType.ASCITES,
            ContentType.SYNOVIAL_FLUID,
            ContentType.BRONCHOALVEOLAR_LAVAGE_FLUID,
        )
    },
    (ContentKind.BIO_FLUID, ContentType.BUFFY_COAT): PartitionClass.COMPOSITE_SAMPLE,
    **{
        (ContentKind.BIO_CELLULAR, content_type): PartitionClass.PELLETABLE_CELLS
        for content_type in (
            ContentType.CELL_LINE,
            ContentType.PRIMARY_CELLS,
            ContentType.CELL_POPULATION,
            ContentType.MICROBIAL_CELLS,
        )
    },
    **{
        (ContentKind.BIO_SUBCELLULAR, content_type): PartitionClass.PELLETABLE_MATERIAL
        for content_type in (
            ContentType.ORGANELLE,
            ContentType.MEMBRANE,
            ContentType.VESICLE,
            ContentType.CYTOSKELETAL_STRUCTURE,
        )
    },
    **{
        (ContentKind.BIO_MOLECULE_OR_VIRUS, content_type): PartitionClass.MOLECULAR_TARGET
        for content_type in (
            ContentType.DNA,
            ContentType.RNA,
            ContentType.PROTEIN,
            ContentType.VIRUS,
        )
    },
    **{
        (ContentKind.BIO_ENTITY, content_type): PartitionClass.SOLID_SAMPLE
        for content_type in (ContentType.ORGANISM, ContentType.ORGAN, ContentType.TISSUE)
    },
    **{
        (ContentKind.CHEMICAL, content_type): PartitionClass.LIQUID_MATRIX
        for content_type in (ContentType.SOLVENT,)
    },
    **{
        (ContentKind.CHEMICAL, content_type): PartitionClass.SOLUBLE_COMPOUND
        for content_type in (ContentType.ORGANIC_COMPOUND, ContentType.INORGANIC_COMPOUND, ContentType.DETERGENT)
    },
    (ContentKind.CHEMICAL, ContentType.DYE): PartitionClass.STAIN_REAGENT,
    **{
        (ContentKind.PARTICULATE, content_type): PartitionClass.CAPTURE_PARTICLE
        for content_type in (ContentType.BEADS, ContentType.RESIN)
    },
    (ContentKind.PARTICULATE, ContentType.PARTICLE): PartitionClass.SOLID_PARTICLE,
    **{
        (ContentKind.FORMULATION, content_type): PartitionClass.LIQUID_MATRIX
        for content_type in (
            ContentType.BUFFER,
            ContentType.MEDIUM,
            ContentType.GRADIENT_MEDIUM,
        )
    },
    (ContentKind.FORMULATION, ContentType.SUPPLEMENT): PartitionClass.SOLUBLE_REAGENT,
    (ContentKind.FORMULATION, ContentType.MASTER_MIX): PartitionClass.LIQUID_REACTION_MATRIX,
}


def partition_sep_material(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    program: dict[str, Any],
    explicit_fates: dict[str, ExplicitContentFate] | None = None,
) -> dict[str, Any]:
    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    strategy = SepPartitionStrategyRegistry().strategy_for(program_kind)
    operation_contract = resolve_separation_operation_contract(
        program,
        slot_contract=strategy.slot_contract,
    )
    author_fates = explicit_fates or {}
    source_components = source.setdefault("components", {})
    source_quantities = source.get("component_quantities")
    source_quantities = source_quantities if isinstance(source_quantities, dict) else {}
    if not isinstance(source_components, dict) or not source_components:
        ratio0, ratio1 = 0.5, 0.5
        source_volume = float(source.get("volume_uL", 0.0))
        source_mass = float(source.get("mass_mg", 0.0))
        set_container_material(
            slot0,
            volume_uL=source_volume * ratio0,
            mass_mg=source_mass * ratio0,
            components={},
            component_quantities={},
        )
        set_container_material(
            slot1,
            volume_uL=source_volume * ratio1,
            mass_mg=source_mass * ratio1,
            components={},
            component_quantities={},
        )
        if source is not slot0 and source is not slot1:
            set_container_material(source, volume_uL=0.0, mass_mg=0.0, components={}, component_quantities={})
        out: dict[str, Any] = {
            "mode": "generic_empty",
            "default_ratio": ratio0,
            "strategy": strategy.program_kind,
            "slot_contract": dict(strategy.slot_contract),
            "operation_contract": operation_contract.to_dict(),
        }
        preservation_contract = strategy.preservation_contract()
        if preservation_contract is not None:
            out["preservation_contract"] = preservation_contract
        return out

    class_resolver = ContentClassResolver()
    slot0_components: dict[str, float] = {}
    slot1_components: dict[str, float] = {}
    slot0_quantities: dict[str, dict[str, Any]] = {}
    slot1_quantities: dict[str, dict[str, Any]] = {}
    slot0_classes: dict[str, str] = {}
    slot1_classes: dict[str, str] = {}
    class_counts: dict[str, int] = {}
    ratios_by_class: dict[str, tuple[float, float]] = {}
    ratios_by_component: dict[str, tuple[float, float]] = {}
    fates_by_component: dict[str, dict[str, Any]] = {}
    fallback_components: list[dict[str, str]] = []

    for name, amount in list(source_components.items()):
        amount_f = float(amount)
        component_id = str(name)
        partition_class = class_resolver.classify(state, source, component_id)
        explicit_fate = author_fates.get(component_id)
        if explicit_fate is None:
            legacy_ratios = _component_partition_ratios(source, component_id)
            if legacy_ratios is not None:
                explicit_fate = ExplicitContentFate(
                    component_id=component_id,
                    ratios=legacy_ratios,
                    declared_slots=("0", "1"),
                    source="source_metadata_override",
                )
        physical_state = resolve_content_physical_state(state, source, component_id)
        fate = resolve_content_fate(
            contract=operation_contract,
            physical_state=physical_state,
            default_ratios=strategy.ratios(partition_class),
            explicit_fate=explicit_fate,
        )
        ratio0, ratio1 = fate.ratios
        if fate.uncertainty_reason is not None or (
            (ratio0, ratio1) == _EQUAL_SPLIT and fate.source == "reference_prediction"
        ):
            fallback_components.append(
                {
                    "component": component_id,
                    "partition_class": partition_class.value,
                    "reason": fate.uncertainty_reason or _partition_fallback_reason(partition_class),
                }
            )
        class_key = partition_class.value
        class_counts[class_key] = class_counts.get(class_key, 0) + 1
        ratios_by_class[class_key] = (ratio0, ratio1)
        ratios_by_component[component_id] = (ratio0, ratio1)
        fates_by_component[component_id] = fate.to_dict()
        slot0_components[component_id] = slot0_components.get(component_id, 0.0) + amount_f * ratio0
        slot1_components[component_id] = slot1_components.get(component_id, 0.0) + amount_f * ratio1
        source_quantity = source_quantities.get(component_id)
        if isinstance(source_quantity, dict):
            quantity_value = float(source_quantity.get("value", amount_f))
            slot0_quantities[component_id] = {
                "dimension": source_quantity.get("dimension"),
                "unit": source_quantity.get("unit"),
                "value": quantity_value * ratio0,
            }
            slot1_quantities[component_id] = {
                "dimension": source_quantity.get("dimension"),
                "unit": source_quantity.get("unit"),
                "value": quantity_value * ratio1,
            }
        slot0_classes[component_id] = strategy.output_class(partition_class, slot="0").value
        slot1_classes[component_id] = strategy.output_class(partition_class, slot="1").value

    source_volume = float(source.get("volume_uL", 0.0))
    source_mass = float(source.get("mass_mg", 0.0))
    set_container_material(
        slot0,
        volume_uL=source_volume * 0.5,
        mass_mg=source_mass * 0.5,
        components=slot0_components,
        component_classes=slot0_classes,
        component_quantities=slot0_quantities,
    )
    set_container_material(
        slot1,
        volume_uL=source_volume * 0.5,
        mass_mg=source_mass * 0.5,
        components=slot1_components,
        component_classes=slot1_classes,
        component_quantities=slot1_quantities,
    )
    bulk_quantity_policy = normalize_partition_slot_bulk_pair(
        slot0,
        slot1,
        source_volume_uL=source_volume,
        source_mass_mg=source_mass,
    )
    if source is not slot0 and source is not slot1:
        set_container_material(source, volume_uL=0.0, mass_mg=0.0, components={}, component_quantities={})

    out = {
        "mode": "program_partition",
        "strategy": strategy.program_kind,
        "slot_contract": dict(strategy.slot_contract),
        "classes": class_counts,
        "ratios_by_class": {name: {"0": ratios[0], "1": ratios[1]} for name, ratios in ratios_by_class.items()},
        "ratios_by_component": {name: {"0": ratios[0], "1": ratios[1]} for name, ratios in ratios_by_component.items()},
        "fates_by_component": fates_by_component,
        "fallback_components": fallback_components,
        "bulk_quantity_policy": bulk_quantity_policy,
        "operation_contract": operation_contract.to_dict(),
    }
    preservation_contract = strategy.preservation_contract()
    if preservation_contract is not None:
        out["preservation_contract"] = preservation_contract
    return out


def normalize_partition_slot_bulk_pair(
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    *,
    source_volume_uL: float,
    source_mass_mg: float,
) -> dict[str, str]:
    slots = (slot0, slot1)
    has_count = any(_has_quantity_dimension(slot, "count") for slot in slots)
    if not has_count:
        return {"volume": "conservative_equal_split", "mass": "conservative_equal_split"}

    for slot in slots:
        normalize_source_partition_slot_bulk(slot)

    has_volume = any(_has_quantity_dimension(slot, "volume") for slot in slots)
    has_mass = any(_has_quantity_dimension(slot, "mass") for slot in slots)
    if not has_volume and not has_mass:
        return {"volume": "conservative_equal_split", "mass": "conservative_equal_split"}

    volume_policy = _normalize_partition_bulk_axis(
        slots,
        key="volume_uL",
        source_total=source_volume_uL,
        explicit_dimension="volume",
        proxy_dimension="mass",
    )
    mass_policy = _normalize_partition_bulk_axis(
        slots,
        key="mass_mg",
        source_total=source_mass_mg,
        explicit_dimension="mass",
        proxy_dimension="volume",
    )
    return {"volume": volume_policy, "mass": mass_policy}


def _normalize_partition_bulk_axis(
    slots: tuple[dict[str, Any], dict[str, Any]],
    *,
    key: str,
    source_total: float,
    explicit_dimension: str,
    proxy_dimension: str,
) -> str:
    explicit_values = [_quantity_dimension_sum(slot, explicit_dimension) for slot in slots]
    explicit_total = sum(explicit_values)
    proxy_values = [_quantity_dimension_sum(slot, proxy_dimension) for slot in slots]
    proxy_total = sum(proxy_values)

    if explicit_total > source_total + 1e-12:
        scale = 0.0 if explicit_total <= 0.0 else max(0.0, source_total) / explicit_total
        for slot, value in zip(slots, explicit_values, strict=True):
            slot[key] = value * scale
        return "component_quantity_scaled_to_source_bulk"

    residual = max(0.0, source_total - explicit_total)
    if residual <= 1e-12:
        for slot, value in zip(slots, explicit_values, strict=True):
            slot[key] = value
        return "component_quantity_sum"

    if proxy_total > 1e-12:
        for slot, explicit_value, proxy_value in zip(slots, explicit_values, proxy_values, strict=True):
            slot[key] = explicit_value + residual * proxy_value / proxy_total
        if explicit_total > 1e-12:
            return "component_quantity_sum_plus_cross_axis_proxy"
        return "carrier_volume_ratio" if proxy_dimension == "volume" else "carrier_mass_ratio"

    existing_values = [max(0.0, float(slot.get(key, 0.0))) for slot in slots]
    existing_total = sum(existing_values)
    if existing_total <= 1e-12:
        existing_values = [1.0, 1.0]
        existing_total = 2.0
    for slot, explicit_value, existing_value in zip(slots, explicit_values, existing_values, strict=True):
        slot[key] = explicit_value + residual * existing_value / existing_total
    return "conservative_equal_split"


def normalize_source_partition_slot_bulk(slot: dict[str, Any]) -> None:
    quantities = slot.get("component_quantities")
    has_count_quantity = isinstance(quantities, dict) and any(
        isinstance(quantity, dict) and quantity.get("dimension") == "count"
        for quantity in quantities.values()
    )
    if isinstance(quantities, dict) and quantities and has_count_quantity:
        volume_total = 0.0
        mass_total = 0.0
        has_volume = False
        has_mass = False
        for quantity in quantities.values():
            if not isinstance(quantity, dict):
                continue
            dimension = quantity.get("dimension")
            value = float(quantity.get("value", 0.0))
            if dimension == "volume":
                has_volume = True
                volume_total += value
            elif dimension == "mass":
                has_mass = True
                mass_total += value
        if has_volume:
            slot["volume_uL"] = volume_total
        if has_mass:
            slot["mass_mg"] = mass_total
        return
    components = slot.get("components")
    if not isinstance(components, dict) or not components:
        return
    amount = sum(float(value) for value in components.values())
    slot["volume_uL"] = amount
    slot["mass_mg"] = amount


def _has_quantity_dimension(slot: dict[str, Any], dimension: str) -> bool:
    quantities = slot.get("component_quantities")
    return isinstance(quantities, dict) and any(
        isinstance(quantity, dict) and quantity.get("dimension") == dimension
        for quantity in quantities.values()
    )


def _quantity_dimension_sum(slot: dict[str, Any], dimension: str) -> float:
    quantities = slot.get("component_quantities")
    if not isinstance(quantities, dict):
        return 0.0
    return sum(
        float(quantity.get("value", 0.0))
        for quantity in quantities.values()
        if isinstance(quantity, dict) and quantity.get("dimension") == dimension
    )


def _partition_fallback_reason(partition_class: PartitionClass) -> str:
    if partition_class == PartitionClass.CUSTOM:
        return "custom_content_classification"
    if partition_class == PartitionClass.UNKNOWN:
        return "unknown_content_classification"
    if partition_class == PartitionClass.COMPOSITE_SAMPLE:
        return "composite_content_classification"
    return "unsupported_program_partition_class"


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
        attrs = meta.get("content_attrs")
        attrs = attrs if isinstance(attrs, dict) else {}
        if not is_standard_content_type(kind_value, type_value):
            normalized = normalize_content_classification(kind_value, type_value)
            if not normalized.changed or not is_standard_content_type(normalized.kind, normalized.type):
                return PartitionClass.UNKNOWN
            kind_value = normalized.kind
            type_value = normalized.type
            merged_attrs = dict(normalized.attrs)
            merged_attrs.update(attrs)
            attrs = merged_attrs
        if str(attrs.get("original_type", "")).startswith("custom_"):
            return PartitionClass.CUSTOM
        kind = parse_content_kind(kind_value)
        content_type = parse_content_type(type_value)
        if kind is None or content_type is None:
            return PartitionClass.UNKNOWN
        if kind == ContentKind.BIO_MOLECULE_OR_VIRUS and content_type in {
            ContentType.DNA,
            ContentType.RNA,
            ContentType.PROTEIN,
            ContentType.VIRUS,
        }:
            return PartitionClass.MOLECULAR_TARGET
        role = str(attrs.get("role", "") or "").lower()
        state_value = str(attrs.get("state", "") or "").lower()
        if state_value in {"lysate", "extract"}:
            return PartitionClass.SOLUBLE_BIOSAMPLE_MATRIX
        if state_value in {"pellet", "washed_pellet"}:
            return PartitionClass.PELLETABLE_MATERIAL
        if state_value in {"suspension", "mixed"}:
            return PartitionClass.PELLETABLE_CELLS
        if role in {"wash"}:
            return PartitionClass.WASH_LIQUID
        if role in {"lysis", "binding", "elution", "storage", "reaction_environment", "density_gradient_separation"}:
            return PartitionClass.PROCESS_LIQUID_MATRIX
        if role in {"precipitation"}:
            return PartitionClass.PRECIPITATION_LIQUID
        if role in {"detection", "stain"}:
            return PartitionClass.STAIN_REAGENT
        if role in {"cleanup", "fragmentation", "ligation", "amplification", "ionization", "anticoagulant"}:
            return PartitionClass.LIQUID_REAGENT
        mapped = _CONTENT_CLASS_BY_KIND_TYPE.get((kind, content_type))
        if mapped is not None:
            return mapped
        return PartitionClass.UNKNOWN


class SepPartitionStrategy:
    program_kind = "sep_program"
    slot_contract: dict[str, str] = {"0": "fraction_0", "1": "fraction_1"}

    def ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in {PartitionClass.CUSTOM, PartitionClass.UNKNOWN, PartitionClass.COMPOSITE_SAMPLE}:
            return _EQUAL_SPLIT
        return self._known_ratios(partition_class)

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        return _EQUAL_SPLIT

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        return partition_class

    def preservation_contract(self) -> dict[str, Any] | None:
        return None

    def cell_material_state(self, *, slot: str) -> str:
        return "suspension"


class CentrifugePartitionStrategy(SepPartitionStrategy):
    program_kind = "centrifuge_program"
    slot_contract = {"0": "supernatant", "1": "pellet"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _PELLET_PARTITION_CLASSES:
            return _NEAR_COMPLETE_TO_SLOT1
        return _NEAR_COMPLETE_TO_SLOT0

    def cell_material_state(self, *, slot: str) -> str:
        return "pellet" if slot == "1" else "suspension"


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
            return _NEAR_COMPLETE_TO_SLOT0
        if partition_class in {
            PartitionClass.LIQUID_REAGENT,
            PartitionClass.PRECIPITATION_LIQUID,
            PartitionClass.STAIN_REAGENT,
            PartitionClass.WASH_LIQUID,
        }:
            return _NEAR_COMPLETE_TO_SLOT1
        return _EQUAL_SPLIT


class PrecipitationPartitionStrategy(SepPartitionStrategy):
    program_kind = "precipitation_program"
    slot_contract = {"0": "precipitate", "1": "supernatant"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES or partition_class in _PELLET_PARTITION_CLASSES:
            return _TARGETED_RECOVERY_TO_SLOT0
        if partition_class in _LIQUID_PARTITION_CLASSES:
            return _NEAR_COMPLETE_TO_SLOT1
        return _EQUAL_SPLIT

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "0" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class

    def cell_material_state(self, *, slot: str) -> str:
        return "precipitate" if slot == "0" else "suspension"


class FiltrationPartitionStrategy(SepPartitionStrategy):
    program_kind = "filtration_program"
    slot_contract = {"0": "filtrate", "1": "retentate"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES or partition_class in _PELLET_PARTITION_CLASSES:
            return _NEAR_COMPLETE_TO_SLOT1
        return _NEAR_COMPLETE_TO_SLOT0

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "1" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class

    def cell_material_state(self, *, slot: str) -> str:
        return "retained" if slot == "1" else "suspension"


class CentrifugalFiltrationPartitionStrategy(FiltrationPartitionStrategy):
    program_kind = "centrifugal_filtration_program"


class MagneticPartitionStrategy(SepPartitionStrategy):
    program_kind = "magnetic_program"
    slot_contract = {"0": "bound", "1": "flowthrough"}

    def preservation_contract(self) -> dict[str, Any] | None:
        return {
            "kind": "field_retention",
            "field": "magnetic_rack",
            "retained_slot": "0",
            "default_incoming_slot": "1",
        }

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class == PartitionClass.CAPTURE_PARTICLE
            or partition_class == PartitionClass.RETAINED_FRACTION
        ):
            return _NEAR_COMPLETE_TO_SLOT0
        return _NEAR_COMPLETE_TO_SLOT1

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        if slot == "0" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class == PartitionClass.CAPTURE_PARTICLE
            or partition_class == PartitionClass.RETAINED_FRACTION
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class

    def cell_material_state(self, *, slot: str) -> str:
        return "retained" if slot == "0" else "suspension"


class DisruptPartitionStrategy(SepPartitionStrategy):
    program_kind = "disrupt_program"
    slot_contract = {"0": "lysate", "1": "debris_or_residue"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _PELLET_PARTITION_CLASSES:
            return _TARGETED_RECOVERY_TO_SLOT1
        return _TARGETED_RECOVERY_TO_SLOT0

    def cell_material_state(self, *, slot: str) -> str:
        return "lysate" if slot == "0" else "debris"


class FieldPartitionStrategy(SepPartitionStrategy):
    program_kind = "field_program"
    slot_contract = {"0": "target_band_fraction", "1": "non_target_fraction"}

    def _known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES:
            return _TARGETED_RECOVERY_TO_SLOT0
        return _TARGETED_RECOVERY_TO_SLOT1


_DEFAULT_SEP_PARTITION_STRATEGY = SepPartitionStrategy()
_SEP_PARTITION_STRATEGIES: dict[str, SepPartitionStrategy] = {
    strategy.program_kind: strategy
    for strategy in (
        CentrifugePartitionStrategy(),
        PhasePartitionStrategy(),
        PrecipitationPartitionStrategy(),
        FiltrationPartitionStrategy(),
        CentrifugalFiltrationPartitionStrategy(),
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


def separation_cell_material_state(program_kind: str, *, slot: str) -> str:
    """Return the program-owned cellular material state for one output slot."""

    return SepPartitionStrategyRegistry().strategy_for(program_kind).cell_material_state(slot=slot)


def separation_slot_contract(program_kind: str) -> dict[str, str]:
    """Return the semantic output names for one separation program."""

    return dict(SepPartitionStrategyRegistry().strategy_for(program_kind).slot_contract)
