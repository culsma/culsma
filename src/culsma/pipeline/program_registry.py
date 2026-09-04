"""Concrete program registry for program-first execution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProgramOutput(Enum):
    """Closed, program-owned identity for one ordered separation output."""

    def __new__(cls, part_id: str, semantic_role: str) -> ProgramOutput:
        member = object.__new__(cls)
        member._value_ = (part_id, semantic_role)
        return member

    @property
    def part_id(self) -> str:
        return self.value[0]

    @property
    def semantic_role(self) -> str:
        return self.value[1]


class SepProgramOutput(ProgramOutput):
    FRACTION_A = ("0", "fraction_0")
    FRACTION_B = ("1", "fraction_1")


class CentrifugeProgramOutput(ProgramOutput):
    SUPERNATANT = ("0", "supernatant")
    PELLET = ("1", "pellet")


class MagneticProgramOutput(ProgramOutput):
    BOUND = ("0", "bound")
    FLOWTHROUGH = ("1", "flowthrough")


class DisruptProgramOutput(ProgramOutput):
    LYSATE = ("0", "lysate")
    DEBRIS_OR_RESIDUE = ("1", "debris_or_residue")


class FieldProgramOutput(ProgramOutput):
    TARGET_BAND_FRACTION = ("0", "target_band_fraction")
    NON_TARGET_FRACTION = ("1", "non_target_fraction")


class FiltrationProgramOutput(ProgramOutput):
    FILTRATE = ("0", "filtrate")
    RETENTATE = ("1", "retentate")


class CentrifugalFiltrationProgramOutput(ProgramOutput):
    FILTRATE = ("0", "filtrate")
    RETENTATE = ("1", "retentate")


class PhasePartitionProgramOutput(ProgramOutput):
    TARGET_PHASE = ("0", "target_phase")
    OTHER_PHASE = ("1", "other_phase")


class PrecipitationProgramOutput(ProgramOutput):
    PRECIPITATE = ("0", "precipitate")
    SUPERNATANT = ("1", "supernatant")


@dataclass(frozen=True)
class ProgramOutputResolution:
    output: ProgramOutput | None = None
    code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        resolved = self.output is not None
        failed = self.code is not None and self.message is not None
        if resolved == failed:
            raise ValueError(
                "ProgramOutputResolution must contain either output or code/message"
            )


@dataclass(frozen=True)
class ProgramFieldSpec:
    name: str
    required: bool
    value_kind: str
    dimension: str | None = None
    enum_values: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ProgramArgAliasSpec:
    name: str
    canonical_name: str
    warning_code: str


@dataclass(frozen=True)
class ProgramSpec:
    kind: str
    family: str
    owners: tuple[str, ...]
    fields: tuple[ProgramFieldSpec, ...]
    required_fields: tuple[str, ...]
    required_one_of: tuple[tuple[str, ...], ...] = ()
    argument_aliases: tuple[ProgramArgAliasSpec, ...] = ()
    allowed_source_styles: tuple[str, ...] | None = None
    result_contract_key: str | None = None
    material_effect_kind: str | None = None
    output_type: type[ProgramOutput] | None = None
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
    required_one_of: tuple[tuple[str, ...], ...] = (),
    argument_aliases: tuple[ProgramArgAliasSpec, ...] = (),
    allowed_source_styles: tuple[str, ...] | None = None,
    result_contract_key: str | None = None,
    material_effect_kind: str | None = None,
    output_type: type[ProgramOutput] | None = None,
    legacy_aliases: tuple[str, ...] = (),
) -> ProgramSpec:
    required_fields = tuple(field.name for field in fields if field.required)
    return ProgramSpec(
        kind=kind,
        family=family,
        owners=owners,
        fields=fields,
        required_fields=required_fields,
        required_one_of=required_one_of,
        argument_aliases=argument_aliases,
        allowed_source_styles=allowed_source_styles,
        result_contract_key=result_contract_key,
        material_effect_kind=material_effect_kind,
        output_type=output_type,
        legacy_aliases=legacy_aliases,
    )


KEEP_SOURCE_VALUES = ("supernatant", "pellet")
DISRUPTION_METHOD_VALUES = (
    "mechanical",
    "sonication",
    "shear_homogenization",
    "high_pressure_disruption",
    "bead_impact",
)

PROGRAM_OUTPUT_TYPES: dict[str, type[ProgramOutput]] = {
    output_type.__name__: output_type
    for output_type in (
        SepProgramOutput,
        CentrifugeProgramOutput,
        MagneticProgramOutput,
        DisruptProgramOutput,
        FieldProgramOutput,
        FiltrationProgramOutput,
        CentrifugalFiltrationProgramOutput,
        PhasePartitionProgramOutput,
        PrecipitationProgramOutput,
    )
}

_LEGACY_PROGRAM_OUTPUT_TYPES: dict[str, type[ProgramOutput]] = {
    "sep_program": SepProgramOutput,
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
        output_type=CentrifugeProgramOutput,
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
        output_type=MagneticProgramOutput,
    ),
    "disrupt_program": _spec(
        "disrupt_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field(
                "method",
                value_kind="text_enum",
                enum_values=DISRUPTION_METHOD_VALUES,
            ),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="disrupt",
        output_type=DisruptProgramOutput,
    ),
    "field_program": _spec(
        "field_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(
            _field("voltage", value_kind="quantity", dimension="electric_potential"),
            _field("current", value_kind="quantity", dimension="electric_current"),
            _field("field", value_kind="quantity", dimension="electric_potential"),
            _field("duration", value_kind="quantity", dimension="time"),
        ),
        required_one_of=(("voltage", "current", "field"),),
        argument_aliases=(
            ProgramArgAliasSpec(
                name="field",
                canonical_name="voltage",
                warning_code="SEM_FIELD_PROGRAM_FIELD_ALIAS",
            ),
        ),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
        output_type=FieldProgramOutput,
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
        output_type=FiltrationProgramOutput,
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
        output_type=CentrifugalFiltrationProgramOutput,
    ),
    "phase_partition_program": _spec(
        "phase_partition_program",
        family="sep",
        owners=("sep", "partition"),
        fields=(_field("solvent", required=True, value_kind="text"),),
        result_contract_key="sep_container_group",
        material_effect_kind="separation_fate",
        output_type=PhasePartitionProgramOutput,
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
        output_type=PrecipitationProgramOutput,
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


def canonical_program_arg_name(program_kind: str, arg_name: str) -> str:
    spec = get_program_spec(program_kind)
    if spec is None:
        return arg_name
    for alias in spec.argument_aliases:
        if alias.name == arg_name:
            return alias.canonical_name
    return arg_name


def get_program_outputs(kind: str) -> tuple[ProgramOutput, ...]:
    spec = get_program_spec(kind)
    output_type = (
        spec.output_type
        if spec is not None
        else _LEGACY_PROGRAM_OUTPUT_TYPES.get(kind)
    )
    return tuple(output_type) if output_type is not None else ()


# Compatibility/serialization view only. ProgramSpec.output_type is authoritative
# for registered programs; this table is derived after registry construction.
SEPARATION_SLOT_CONTRACTS: dict[str, dict[str, str]] = {
    kind: {
        output.part_id: output.semantic_role
        for output in get_program_outputs(kind)
    }
    for kind in (
        *_LEGACY_PROGRAM_OUTPUT_TYPES,
        *(
            program_kind
            for program_kind, spec in PROGRAM_REGISTRY.items()
            if spec.output_type is not None
        ),
    )
}


def resolve_program_output(
    program_kind: str,
    enum_type_name: str,
    member_name: str,
) -> ProgramOutputResolution:
    expected_outputs = get_program_outputs(program_kind)
    if not expected_outputs:
        return ProgramOutputResolution(
            code="PROGRAM_OUTPUT_PROGRAM_UNKNOWN",
            message=f"Program '{program_kind}' does not declare separation outputs",
        )
    expected_type = type(expected_outputs[0])
    requested_type = PROGRAM_OUTPUT_TYPES.get(enum_type_name)
    if requested_type is not expected_type:
        return ProgramOutputResolution(
            code="PROGRAM_OUTPUT_ENUM_TYPE_MISMATCH",
            message=(
                f"Program '{program_kind}' requires {expected_type.__name__}, "
                f"not '{enum_type_name}'"
            ),
        )
    try:
        output = requested_type[member_name]
    except KeyError:
        return ProgramOutputResolution(
            code="PROGRAM_OUTPUT_MEMBER_UNKNOWN",
            message=(
                f"{enum_type_name} has no member '{member_name}'"
            ),
        )
    return ProgramOutputResolution(output=output)


def get_separation_slot_contract(kind: str) -> dict[str, str] | None:
    outputs = get_program_outputs(kind)
    if not outputs:
        return None
    return {output.part_id: output.semantic_role for output in outputs}


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
