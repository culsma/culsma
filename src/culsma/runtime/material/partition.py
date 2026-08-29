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
from culsma.pipeline.program_registry import get_separation_slot_contract
from culsma.runtime.material.ledger import refresh_container_aggregates, set_container_material
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


def parse_partition_class(value: str) -> PartitionClass:
    try:
        return PartitionClass(value)
    except ValueError:
        return PartitionClass.UNKNOWN


def component_partition_ratios(
    container: dict[str, Any],
    component_id: str,
) -> tuple[float, float] | None:
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


def apply_legacy_partition_material(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    program: dict[str, Any],
    explicit_fates: dict[str, ExplicitContentFate] | None = None,
) -> dict[str, Any]:
    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    slot_contract = get_separation_slot_contract(program_kind) or {
        "0": "fraction_0",
        "1": "fraction_1",
    }
    operation_contract = resolve_separation_operation_contract(
        program,
        slot_contract=slot_contract,
    )
    author_fates = explicit_fates or {}
    source_components = source.setdefault("components", {})
    source_quantities = source.get("component_quantities")
    source_quantities = source_quantities if isinstance(source_quantities, dict) else {}
    if not isinstance(source_components, dict):
        source_components = {}

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

    strategy = SepPartitionStrategyRegistry().strategy_for(program_kind)
    for name, amount in list(source_components.items()):
        component_id = str(name)
        explicit_fate = author_fates.get(component_id)
        if explicit_fate is None:
            legacy_ratios = component_partition_ratios(source, component_id)
            if legacy_ratios is not None:
                explicit_fate = ExplicitContentFate(
                    component_id=component_id,
                    ratios=legacy_ratios,
                    declared_slots=("0", "1"),
                    source="source_metadata_override",
                )
        amount_f = float(amount)
        partition_class = class_resolver.classify(state, source, component_id)
        physical_state = resolve_content_physical_state(
            state, source, component_id
        )
        fate = resolve_content_fate(
            contract=operation_contract,
            physical_state=physical_state,
            default_ratios=(
                _EQUAL_SPLIT
                if partition_class is None
                else strategy.ratios(partition_class)
            ),
            explicit_fate=explicit_fate,
        )
        ratio0, ratio1 = fate.ratios
        if partition_class is not None and (
            fate.uncertainty_reason is not None
            or (
                (ratio0, ratio1) == _EQUAL_SPLIT
                and fate.source == "reference_prediction"
            )
        ):
            fallback_components.append(
                {
                    "component": component_id,
                    "partition_class": partition_class.value,
                    "reason": fate.uncertainty_reason or partition_fallback_reason(partition_class),
                }
            )
        if partition_class is not None:
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
            slot0_quantities[component_id] = dict(source_quantity)
            slot0_quantities[component_id]["value"] = quantity_value * ratio0
            slot1_quantities[component_id] = dict(source_quantity)
            slot1_quantities[component_id]["value"] = quantity_value * ratio1
        if partition_class is not None:
            slot0_classes[component_id] = strategy.output_class(
                partition_class, slot="0"
            ).value
            slot1_classes[component_id] = strategy.output_class(
                partition_class, slot="1"
            ).value

    set_container_material(
        slot0,
        components=slot0_components,
        component_classes=slot0_classes,
        component_quantities=slot0_quantities,
    )
    set_container_material(
        slot1,
        components=slot1_components,
        component_classes=slot1_classes,
        component_quantities=slot1_quantities,
    )
    bulk_quantity_policy = project_partition_slot_aggregates(slot0, slot1)
    if source is not slot0 and source is not slot1:
        set_container_material(source, components={}, component_quantities={})

    out = {
        "mode": "program_partition",
        "strategy": strategy.program_kind,
        "slot_contract": dict(slot_contract),
        "classes": class_counts,
        "ratios_by_class": {name: {"0": ratios[0], "1": ratios[1]} for name, ratios in ratios_by_class.items()},
        "ratios_by_component": {
            name: {"0": ratios[0], "1": ratios[1]}
            for name, ratios in ratios_by_component.items()
        },
        "fates_by_component": fates_by_component,
        "transitions_by_component": {},
        "fallback_components": fallback_components,
        "bulk_quantity_policy": bulk_quantity_policy,
        "operation_contract": operation_contract.to_dict(),
    }
    preservation_contract = strategy.preservation_contract()
    if preservation_contract is not None:
        out["preservation_contract"] = preservation_contract
    return out


def project_partition_slot_aggregates(
    slot0: dict[str, Any],
    slot1: dict[str, Any],
) -> dict[str, str]:
    """Project both aggregate caches only from each slot's routed detail."""

    refresh_container_aggregates(slot0)
    refresh_container_aggregates(slot1)
    return {"volume": "detail_ledger_projection", "mass": "detail_ledger_projection"}


def partition_fallback_reason(partition_class: PartitionClass) -> str:
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
                    return parse_partition_class(override)
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
    """Compatibility API; Runtime separation does not dispatch through it."""

    program_kind = "sep_program"

    def ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in {PartitionClass.CUSTOM, PartitionClass.UNKNOWN, PartitionClass.COMPOSITE_SAMPLE}:
            return _EQUAL_SPLIT
        return self.known_ratios(partition_class)

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        return _EQUAL_SPLIT

    def output_class(self, partition_class: PartitionClass, *, slot: str) -> PartitionClass:
        return partition_class

    def preservation_contract(self) -> dict[str, Any] | None:
        return None

    def cell_material_state(self, *, slot: str) -> str:
        return "suspension"


class PhasePartitionStrategy(SepPartitionStrategy):
    program_kind = "phase_partition_program"

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
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

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return _TARGETED_RECOVERY_TO_SLOT0
        if partition_class in _LIQUID_PARTITION_CLASSES:
            return _NEAR_COMPLETE_TO_SLOT1
        return _EQUAL_SPLIT

    def output_class(
        self,
        partition_class: PartitionClass,
        *,
        slot: str,
    ) -> PartitionClass:
        if slot == "0" and (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class in _PELLET_PARTITION_CLASSES
        ):
            return PartitionClass.RETAINED_FRACTION
        return partition_class

    def cell_material_state(self, *, slot: str) -> str:
        return "precipitate" if slot == "0" else "suspension"


class MagneticPartitionStrategy(SepPartitionStrategy):
    program_kind = "magnetic_program"

    def preservation_contract(self) -> dict[str, Any] | None:
        return {
            "kind": "field_retention",
            "field": "magnetic_rack",
            "retained_slot": "0",
            "default_incoming_slot": "1",
        }

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if (
            partition_class in _TARGET_PARTITION_CLASSES
            or partition_class == PartitionClass.CAPTURE_PARTICLE
            or partition_class == PartitionClass.RETAINED_FRACTION
        ):
            return _NEAR_COMPLETE_TO_SLOT0
        return _NEAR_COMPLETE_TO_SLOT1

    def output_class(
        self,
        partition_class: PartitionClass,
        *,
        slot: str,
    ) -> PartitionClass:
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

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _PELLET_PARTITION_CLASSES:
            return _TARGETED_RECOVERY_TO_SLOT1
        return _TARGETED_RECOVERY_TO_SLOT0

    def cell_material_state(self, *, slot: str) -> str:
        return "lysate" if slot == "0" else "debris"


class FieldPartitionStrategy(SepPartitionStrategy):
    program_kind = "field_program"

    def known_ratios(self, partition_class: PartitionClass) -> tuple[float, float]:
        if partition_class in _TARGET_PARTITION_CLASSES:
            return _TARGETED_RECOVERY_TO_SLOT0
        return _TARGETED_RECOVERY_TO_SLOT1


_DEFAULT_SEP_PARTITION_STRATEGY = SepPartitionStrategy()
_SEP_PARTITION_STRATEGIES: dict[str, SepPartitionStrategy] = {
    strategy.program_kind: strategy
    for strategy in (
        PhasePartitionStrategy(),
        PrecipitationPartitionStrategy(),
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


def sep_partition_strategy(program_kind: str) -> SepPartitionStrategy:
    return SepPartitionStrategyRegistry().strategy_for(program_kind)


def legacy_separation_cell_material_state(
    program_kind: str,
    *,
    slot: str,
) -> str:
    """Return the legacy strategy's cellular state for one output slot."""

    return SepPartitionStrategyRegistry().strategy_for(
        program_kind
    ).cell_material_state(slot=slot)
