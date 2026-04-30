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
        legacy_aliases=legacy_aliases,
    )


KEEP_SOURCE_VALUES = ("supernatant", "pellet")
ACQ_TYPE_VALUES = ("snapshot", "time_series", "z_stack", "single")


PROGRAM_REGISTRY: dict[str, ProgramSpec] = {
    "pipette_program": _spec(
        "pipette_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(
            _field("tip", value_kind="text"),
            _field("volume", value_kind="quantity", dimension="volume"),
            _field("cycles", value_kind="int"),
        ),
        allowed_source_styles=("quantified", "full"),
    ),
    "vortex_program": _spec(
        "vortex_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(
            _field("duration", required=True, value_kind="quantity", dimension="time"),
            _field("speed", value_kind="quantity", dimension="rotation_rate"),
        ),
        allowed_source_styles=("full",),
    ),
    "invert_program": _spec(
        "invert_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(_field("times", required=True, value_kind="int"),),
        allowed_source_styles=("full",),
    ),
    "shake_program": _spec(
        "shake_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(
            _field("duration", required=True, value_kind="quantity", dimension="time"),
            _field("speed", value_kind="quantity", dimension="rotation_rate"),
            _field("mode", value_kind="text"),
        ),
        allowed_source_styles=("full",),
    ),
    "plate_shake_program": _spec(
        "plate_shake_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(
            _field("duration", required=True, value_kind="quantity", dimension="time"),
            _field("speed", value_kind="quantity", dimension="rotation_rate"),
        ),
        allowed_source_styles=("full",),
    ),
    "stir_program": _spec(
        "stir_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(
            _field("duration", value_kind="quantity", dimension="time"),
            _field("speed", value_kind="quantity", dimension="rotation_rate"),
        ),
        allowed_source_styles=("full",),
    ),
    "spatula_program": _spec(
        "spatula_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(),
        allowed_source_styles=("quantified",),
    ),
    "scalpel_program": _spec(
        "scalpel_program",
        family="mutation",
        owners=("mutation_stmt",),
        fields=(),
        allowed_source_styles=("quantified",),
    ),
    "centrifuge_program": _spec(
        "centrifuge_program",
        family="sep",
        owners=("sep",),
        fields=(
            _field("drive", required=True, value_kind="quantity", dimension="centrifuge_speed"),
            _field("keep_source", value_kind="text_enum", enum_values=KEEP_SOURCE_VALUES),
        ),
        result_contract_key="sep_container_group",
    ),
    "magnetic_program": _spec(
        "magnetic_program",
        family="sep",
        owners=("sep",),
        fields=(
            _field("duration", value_kind="quantity", dimension="time"),
            _field("device", value_kind="text"),
        ),
        result_contract_key="sep_container_group",
    ),
    "disrupt_program": _spec(
        "disrupt_program",
        family="sep",
        owners=("sep",),
        fields=(_field("duration", value_kind="quantity", dimension="time"),),
        result_contract_key="sep_container_group",
    ),
    "field_program": _spec(
        "field_program",
        family="sep",
        owners=("sep",),
        fields=(
            _field("field", required=True, value_kind="quantity", dimension="electric_potential"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
    ),
    "filtration_program": _spec(
        "filtration_program",
        family="sep",
        owners=("sep",),
        fields=(
            _field("membrane", required=True, value_kind="text"),
            _field("drive", required=True, value_kind="text"),
        ),
        result_contract_key="sep_container_group",
    ),
    "phase_partition_program": _spec(
        "phase_partition_program",
        family="sep",
        owners=("sep",),
        fields=(_field("solvent", required=True, value_kind="text"),),
        result_contract_key="sep_container_group",
    ),
    "precipitation_program": _spec(
        "precipitation_program",
        family="sep",
        owners=("sep",),
        fields=(
            _field("reagent", required=True, value_kind="text"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
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
    "optical_uv_program": _spec(
        "optical_uv_program",
        family="image",
        owners=("img",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("device", value_kind="text"),
            _field("channels", value_kind="list"),
        ),
        result_contract_key="observation_ref",
    ),
    "optical_fluor_program": _spec(
        "optical_fluor_program",
        family="image",
        owners=("img",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("device", value_kind="text"),
            _field("channels", value_kind="list"),
        ),
        result_contract_key="observation_ref",
    ),
    "optical_colorimetric_program": _spec(
        "optical_colorimetric_program",
        family="image",
        owners=("img",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("device", value_kind="text"),
            _field("channels", value_kind="list"),
        ),
        result_contract_key="observation_ref",
    ),
    "gel_readout_program": _spec(
        "gel_readout_program",
        family="image",
        owners=("img",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("device", value_kind="text"),
            _field("channels", value_kind="list"),
            _field("exposure", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="observation_ref",
    ),
    "microscopy_program": _spec(
        "microscopy_program",
        family="image",
        owners=("img",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("device", value_kind="text"),
            _field("channels", value_kind="list"),
        ),
        result_contract_key="observation_ref",
    ),
    "ph_program": _spec(
        "ph_program",
        family="ecp",
        owners=("ecp",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("stabilize", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="observation_ref",
    ),
    "conductivity_program": _spec(
        "conductivity_program",
        family="ecp",
        owners=("ecp",),
        fields=(
            _field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),
            _field("interval", value_kind="quantity", dimension="time"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="observation_ref",
    ),
    "dissolved_oxygen_program": _spec(
        "dissolved_oxygen_program",
        family="ecp",
        owners=("ecp",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "orp_program": _spec(
        "orp_program",
        family="ecp",
        owners=("ecp",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "ion_selective_program": _spec(
        "ion_selective_program",
        family="ecp",
        owners=("ecp",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "temperature_measure_program": _spec(
        "temperature_measure_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "pressure_program": _spec(
        "pressure_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "flow_rate_program": _spec(
        "flow_rate_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "mass_measure_program": _spec(
        "mass_measure_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "volume_measure_program": _spec(
        "volume_measure_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
    ),
    "humidity_program": _spec(
        "humidity_program",
        family="phy",
        owners=("phy",),
        fields=(_field("acq_type", value_kind="text_enum", enum_values=ACQ_TYPE_VALUES),),
        result_contract_key="observation_ref",
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


def is_known_program_kind(kind: str) -> bool:
    return kind in PROGRAM_REGISTRY


def is_legacy_generic_program(kind: str) -> bool:
    return kind in LEGACY_GENERIC_PROGRAMS


def program_tool_label(kind: str) -> str | None:
    if kind == "pipette_program":
        return "Pipette"
    if kind == "vortex_program":
        return "Vortex"
    if kind == "invert_program":
        return "Invert"
    if kind == "shake_program":
        return "Shaker"
    if kind == "plate_shake_program":
        return "PlateShake"
    if kind == "stir_program":
        return "Stirring"
    if kind == "spatula_program":
        return "Spatula"
    if kind == "scalpel_program":
        return "Scalpel"
    return None
