"""Domain ownership, nominal typing, compatibility and stable wire contracts."""
from enum import Enum, StrEnum
import importlib
import json
from pathlib import Path
import ast

import pytest

from culsma.domains.agitation import AGITATION_MODE, AgitationMode
from culsma.common.enum_parameters import EnumParameter
from culsma.domains.fractionation import DENSITY_GRADIENT_AXIS, DENSITY_GRADIENT_ORDER
from culsma.domains.labware import PLATE_FORMAT, PlateFormat, plate_dimensions, plate_default_well_capacity
from culsma.domains.readout import READOUT_QUANTITIES, ReadoutQuantity, validate_readout_quantity
from culsma.domains.scheduling import SCHEDULE_MODE, DEFAULT_SCHEDULE_MODE, ScheduleMode
from culsma.domains.separation import CENTRIFUGE_KEEP_SOURCE, DISRUPTION_METHOD, CentrifugeProgramOutput
from culsma.pipeline.compat.external_enums import resolve_legacy_enum
from culsma.pipeline import program_registry

CONTRACTS = [AGITATION_MODE, PLATE_FORMAT, CENTRIFUGE_KEEP_SOURCE, DISRUPTION_METHOD,
             DENSITY_GRADIENT_AXIS, DENSITY_GRADIENT_ORDER, SCHEDULE_MODE, *READOUT_QUANTITIES.values()]


@pytest.mark.parametrize('contract', CONTRACTS)
def test_legacy_conversion_and_json_roundtrip_preserve_exact_member(contract):
    for member in contract.allowed_members:
        wire = contract.encode(member)
        assert resolve_legacy_enum(wire, contract) is member
        assert resolve_legacy_enum(member, contract) is member
        assert contract.decode(json.loads(json.dumps(wire))) is member
        with pytest.raises(TypeError):
            contract.validate(wire)
    with pytest.raises(ValueError):
        resolve_legacy_enum('not_a_standard_value', contract)
    for invalid in (None, 42, True, [], {}):
        with pytest.raises(TypeError):
            resolve_legacy_enum(invalid, contract)


@pytest.mark.parametrize('contract', CONTRACTS)
def test_equal_text_does_not_allow_another_enum_family(contract):
    member = next(iter(contract.allowed_members))
    Other = StrEnum('Other', {'VALUE': contract.encode(member)})
    with pytest.raises(TypeError):
        contract.validate(Other.VALUE)
    with pytest.raises(TypeError):
        resolve_legacy_enum(Other.VALUE, contract)
    with pytest.raises(TypeError):
        EnumParameter(contract.enum_type, frozenset({Other.VALUE}))


def test_contract_invariants_and_closed_enum_extension():
    with pytest.raises(TypeError):
        EnumParameter(str)
    with pytest.raises(ValueError):
        EnumParameter(ScheduleMode, frozenset())
    with pytest.raises(TypeError):
        class ExtraScheduleMode(ScheduleMode):
            EXTRA = 'extra'
    class BadWire(Enum):
        NUMBER = 1
    with pytest.raises(TypeError):
        EnumParameter(BadWire)


def test_readout_membership_and_custom_schema_are_independent_requirements():
    assert validate_readout_quantity('img', ReadoutQuantity.FLUORESCENCE, has_schema=False) is ReadoutQuantity.FLUORESCENCE
    with pytest.raises(ValueError):
        validate_readout_quantity('ecp', ReadoutQuantity.FLUORESCENCE, has_schema=True)
    for operation in ('img', 'ecp', 'phy'):
        with pytest.raises(ValueError, match='schema_ref'):
            validate_readout_quantity(operation, ReadoutQuantity.CUSTOMIZED, has_schema=False)
        assert validate_readout_quantity(operation, ReadoutQuantity.CUSTOMIZED, has_schema=True) is ReadoutQuantity.CUSTOMIZED
    with pytest.raises(TypeError):
        validate_readout_quantity('img', 'fluorescence', has_schema=False)


def test_plate_geometry_capacity_and_schedule_default_preserved():
    assert plate_dimensions(PlateFormat.WELL_96) == (8, 12)
    assert plate_dimensions(PlateFormat.WELL_384) == (16, 24)
    assert plate_default_well_capacity(PlateFormat.WELL_24) == (3.4, 'mL')
    assert plate_default_well_capacity(PlateFormat.WELL_96) is None
    with pytest.raises(TypeError):
        plate_dimensions('96well')
    assert DEFAULT_SCHEDULE_MODE is ScheduleMode.DISCRETE
    assert AgitationMode.FLICK in AGITATION_MODE.allowed_members


def test_output_imports_retain_identity_and_role_wire_format():
    from culsma.domains import separation
    for name in program_registry.PROGRAM_OUTPUT_TYPES:
        assert program_registry.PROGRAM_OUTPUT_TYPES[name] is getattr(separation, name)
    assert program_registry.CentrifugeProgramOutput is CentrifugeProgramOutput
    assert CENTRIFUGE_KEEP_SOURCE.encode(CentrifugeProgramOutput.PELLET) == 'pellet'
    assert CentrifugeProgramOutput.PELLET.part_id == '1'
    assert program_registry.KEEP_SOURCE_VALUES == ('supernatant', 'pellet')


def test_pipeline_views_are_derived_from_domain_contracts():
    from culsma.pipeline.validate.statement_contracts import AGIT_MODES, READOUT_QUANTITY_SETS
    from culsma.pipeline.compile.targets import _PLATE_FORMAT_DIMENSIONS
    assert AGIT_MODES == frozenset(AGITATION_MODE.wire_values)
    assert READOUT_QUANTITY_SETS == {op: frozenset(c.wire_values) for op, c in READOUT_QUANTITIES.items()}
    assert set(_PLATE_FORMAT_DIMENSIONS) == set(PLATE_FORMAT.wire_values)
    assert program_registry.DISRUPTION_METHOD_VALUES == DISRUPTION_METHOD.wire_values


def test_domain_contracts_do_not_import_pipeline_runtime_or_drivers():
    import culsma.domains
    root = Path(culsma.domains.__file__).parent
    for path in root.glob('*.py'):
        importlib.import_module(f'culsma.domains.{path.stem}')
        for node in ast.walk(ast.parse(path.read_text())):
            imports = [node.module or ''] if isinstance(node, ast.ImportFrom) else [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            assert not any(name.startswith(('culsma.pipeline', 'culsma.runtime', 'culsma.driver', 'culsma.parser')) for name in imports), path
