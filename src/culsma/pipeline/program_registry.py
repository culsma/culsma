"""Concrete program registry for program-first execution contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramFieldSpec:
    name: str
    required: bool
    value_kind: str
    dimension: str | None = None
    enum_values: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ProgramSpec:
    kind: str
    family: str
    owners: tuple[str, ...]
    fields: tuple[ProgramFieldSpec, ...]
    required_fields: tuple[str, ...]
    allowed_source_styles: tuple[str, ...] | None = None
    result_contract_key: str | None = None
    material_effect_kind: str | None = None
    legacy_aliases: tuple[str, ...] = ()


def _field(
    name: str,
    *,
    required: bool = False,
    value_kind: str = "text",
    dimension: str | None = None,
    enum_values: tuple[str, ...] | None = None,
) -> ProgramFieldSpec:
    return ProgramFieldSpec(
        name=name,
        required=required,
        value_kind=value_kind,
        dimension=dimension,
        enum_values=enum_values,
    )


def _spec(
    kind: str,
    *,
    family: str,
    owners: tuple[str, ...],
    fields: tuple[ProgramFieldSpec, ...],
    allowed_source_styles: tuple[str, ...] | None = None,
    result_contract_key: str | None = None,
    material_effect_kind: str | None = None,
    legacy_aliases: tuple[str, ...] = (),
) -> ProgramSpec:
    required_fields = tuple(field.name for field in fields if field.required)
    return ProgramSpec(
        kind=kind,
        family=family,
        owners=owners,
        fields=fields,
        required_fields=required_fields,
        allowed_source_styles=allowed_source_styles,
        result_contract_key=result_contract_key,
        material_effect_kind=material_effect_kind,
        legacy_aliases=legacy_aliases,
    )


KEEP_SOURCE_VALUES = ("supernatant", "pellet")

SEPARATION_SLOT_CONTRACTS: dict[str, dict[str, str]] = {
    "sep_program": {"0": "fraction_0", "1": "fraction_1"},
    "centrifuge_program": {"0": "supernatant", "1": "pellet"},
    "magnetic_program": {"0": "bound", "1": "flowthrough"},
    "disrupt_program": {"0": "lysate", "1": "debris_or_residue"},
    "field_program": {"0": "target_band_fraction", "1": "non_target_fraction"},
    "filtration_program": {"0": "filtrate", "1": "retentate"},
    "centrifugal_filtration_program": {"0": "filtrate", "1": "retentate"},
    "phase_partition_program": {"0": "target_phase", "1": "other_phase"},
    "precipitation_program": {"0": "precipitate", "1": "supernatant"},
}


PROGRAM_REGISTRY: dict[str, ProgramSpec] = {
    "centrifuge_program": _spec(
        "centrifuge_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("drive", required=True, value_kind="quantity", dimension="centrifuge_speed"),
            _field("keep_source", value_kind="text_enum", enum_values=KEEP_SOURCE_VALUES),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "magnetic_program": _spec(
        "magnetic_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("duration", value_kind="quantity", dimension="time"),
            _field("device", value_kind="text"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "disrupt_program": _spec(
        "disrupt_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(_field("duration", value_kind="quantity", dimension="time"),),
        result_contract_key="sep_container_group",
        material_effect_kind="disrupt",
    ),
    "field_program": _spec(
        "field_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("field", required=True, value_kind="quantity", dimension="electric_potential"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "filtration_program": _spec(
        "filtration_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("membrane", required=True, value_kind="text"),
            _field("drive", required=True, value_kind="text"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "centrifugal_filtration_program": _spec(
        "centrifugal_filtration_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("membrane", required=True, value_kind="text"),
            _field("drive", required=True, value_kind="quantity", dimension="centrifuge_speed"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "phase_partition_program": _spec(
        "phase_partition_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(_field("solvent", required=True, value_kind="text"),),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "precipitation_program": _spec(
        "precipitation_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("reagent", required=True, value_kind="text"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
    ),
    "density_gradient_program": _spec(
        "density_gradient_program",
        family="frac",
        owners=("frac",),
        fields=(
            _field("axis", required=True, value_kind="text_enum", enum_values=("density",)),
            _field("order", required=True, value_kind="text_enum", enum_values=("top_to_bottom", "bottom_to_top")),
            _field("bins", required=True, value_kind="int"),
        ),
        result_contract_key="fraction_group",
    ),
    "chromatography_program": _spec(
        "chromatography_program",
        family="frac",
        owners=("frac",),
        fields=(
            _field("axis", required=True, value_kind="text"),
            _field("order", required=True, value_kind="text"),
            _field("bins", required=True, value_kind="int"),
        ),
        result_contract_key="fraction_group",
    ),
    "thermal_program": _spec(
        "thermal_program",
        family="thermal",
        owners=("with_env",),
        fields=(
            _field("from", value_kind="quantity", dimension="temperature"),
            _field("to", value_kind="quantity", dimension="temperature"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
    ),
}


LEGACY_GENERIC_PROGRAMS = frozenset(
    {
        "sep_program",
        "frac_program",
        "image_program",
        "ec_program",
        "phys_program",
    }
)


def get_program_spec(kind: str) -> ProgramSpec | None:
    return PROGRAM_REGISTRY.get(kind)


def get_separation_slot_contract(kind: str) -> dict[str, str] | None:
    contract = SEPARATION_SLOT_CONTRACTS.get(kind)
    return dict(contract) if contract is not None else None


def get_material_effect_kind(kind: str) -> str | None:
    spec = get_program_spec(kind)
    return spec.material_effect_kind if spec is not None else None


def is_known_program_kind(kind: str) -> bool:
    return kind in PROGRAM_REGISTRY


def is_legacy_generic_program(kind: str) -> bool:
    return kind in LEGACY_GENERIC_PROGRAMS


def program_tool_label(kind: str) -> str | None:
    del kind
    return None
