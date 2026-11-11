"""Direct tests of medium parsing, validation, and reference resolution."""
import pytest

from culsma.domains.medium import CompositionBasis, normalize_liquid_contents
from culsma.parser.ast_nodes import Arg, Identifier, Quantity, RecordLiteral
from culsma.parser.transformer_rules import lower_liquid_contents_argument
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRQuantity
from culsma.pipeline.medium_boundary import (
    decode_descriptor_enum,
    decode_descriptor_literal,
    decode_liquid_contents,
    encode_medium_quantity,
    parse_descriptor_arguments,
    validate_descriptor_fields,
)
from culsma.pipeline.typecheck.expressions import DEFAULT_TYPECHECK_EXPRESSION_SERVICES
from culsma.pipeline.typecheck.medium import DeferredMedium, check_medium_source_reference, serialize_medium_expression
from culsma.runtime.environment_media import resolve_medium_targets
from culsma.runtime.state import RuntimeState
from culsma.runtime.values import resolve_medium_source


def test_lower_liquid_contents_argument_keeps_references_and_repeated_keys():
    name = Identifier("water")
    first = Quantity(75, "%")
    second = Quantity(25, "%")
    arg = Arg("contents", RecordLiteral(entries={"water": second}, key_items=[(name, first), (name, second)]))

    lowered = lower_liquid_contents_argument(arg)

    assert lowered.value.name == "$contents_map"
    pairs = lowered.value.args[0].value.elements
    assert [(pair.left, pair.right) for pair in pairs] == [(name, first), (name, second)]


def test_parse_descriptor_arguments_rejects_duplicates():
    entry = {"name": "source", "value": "reference"}
    assert parse_descriptor_arguments({"args": [entry]}) == {"source": "reference"}
    with pytest.raises(ValueError, match="duplicate"):
        parse_descriptor_arguments({"args": [entry, entry]})


def test_validate_descriptor_fields_requires_exact_fields():
    assert validate_descriptor_fields({"volume": 1}, {"volume"}, {"volume"}) == {"volume": 1}
    with pytest.raises(ValueError, match="medium fields"):
        validate_descriptor_fields({"volme": 1}, {"volume"}, {"volume"})


def test_decode_descriptor_enum_distinguishes_source_and_wire():
    basis = CompositionBasis.VOLUME_FRACTION
    assert decode_descriptor_enum(
        {"kind": "ExternalEnum", "enum": "CompositionBasis", "member": "VOLUME_FRACTION"},
        CompositionBasis,
    ) is basis
    assert decode_descriptor_enum(basis.value, CompositionBasis, allow_wire_text=True) is basis
    with pytest.raises(ValueError, match="CompositionBasis"):
        decode_descriptor_enum(basis.value, CompositionBasis)


def test_decode_descriptor_literal_reads_quantity_and_string():
    assert decode_descriptor_literal({"kind": "IRQuantity", "value": 80, "unit": "%"}) == (80, "%")
    assert decode_descriptor_literal({"kind": "IRString", "value": "WATER"}) == "WATER"


def test_encode_medium_quantity_preserves_unit():
    assert encode_medium_quantity((500, "mL")) == {"kind": "IRQuantity", "value": 500, "unit": "mL"}


def test_decode_liquid_contents_validates_resolved_identity():
    content = {"kind": "IRCall", "name": "DefineContent", "args": [
        {"name": "kind", "value": {"kind": "ContentEnum", "enum": "ContentKind", "member": "CHEMICAL"}},
        {"name": "type", "value": {"kind": "ContentEnum", "enum": "ContentType", "member": "SOLVENT"}},
        {"name": "code", "value": {"kind": "IRString", "value": "WATER"}},
    ]}
    entry = {"kind": "IRPair", "left": content, "right": {"kind": "IRQuantity", "value": 100, "unit": "%"}}
    entries = [entry]
    contents = {"kind": "IRCall", "name": "$contents_map", "args": [
        {"name": "entries", "value": {"kind": "IRList", "elements": entries}},
    ]}

    assert decode_liquid_contents(contents) == {"WATER": (100, "%")}
    entries.append(entry)
    with pytest.raises(ValueError, match="duplicate liquid medium content 'WATER'"):
        decode_liquid_contents(contents)


def test_normalize_liquid_contents_uses_one_basis_and_total():
    contents = {"WATER": (1, "mL"), "ETHANOL": (500, "uL")}
    assert normalize_liquid_contents(contents) == ({"WATER": (1000, "uL"), "ETHANOL": (500, "uL")}, (1500, "uL"))
    with pytest.raises(ValueError, match="sum of its contents"):
        normalize_liquid_contents(contents, volume=(1, "mL"))
    with pytest.raises(ValueError, match="total 100%"):
        normalize_liquid_contents({"WATER": (99, "%")}, basis=CompositionBasis.VOLUME_FRACTION)


def test_serialize_medium_expression_resolves_typed_values():
    services = DEFAULT_TYPECHECK_EXPRESSION_SERVICES
    assert serialize_medium_expression(IRIdentifier("fraction"), {"fraction": IRQuantity(80, "%")}, services) == {
        "kind": "IRQuantity", "value": 80, "unit": "%",
    }
    assert serialize_medium_expression(IRMember(IRIdentifier("ContentKind"), "CHEMICAL"), {}, services) == {
        "kind": "ContentEnum", "enum": "ContentKind", "member": "CHEMICAL",
    }
    with pytest.raises(DeferredMedium):
        serialize_medium_expression(IRIdentifier("unbound"), {}, services)


def test_check_medium_source_reference_requires_container_shape():
    assert check_medium_source_reference({"kind": "IRPlateWellRef"}) == "<deferred-well-identity>"
    assert check_medium_source_reference({"kind": "IRCall", "name": "AllocContainer"}) == "<deferred-container-identity>"
    with pytest.raises(ValueError, match="container reference"):
        check_medium_source_reference({"kind": "IRString", "value": "bath"})


def test_resolve_medium_source_requires_live_container():
    state = RuntimeState(artifacts={"material_state": {"containers": {"bath-id": {}}}})
    assert resolve_medium_source({"kind": "container_ref", "id": "bath-id"}, state) == "bath-id"
    assert resolve_medium_source({"kind": "container_ref", "id": "unknown"}, state) is None


def test_resolve_medium_targets_matches_container_and_contents():
    state = RuntimeState(artifacts={"material_state": {"containers": {"sample-id": {}}}})
    sample = {"kind": "container_ref", "id": "sample-id"}
    contents = {"kind": "IRMember", "base": sample, "member": "contents"}
    assert resolve_medium_targets([sample, contents], state) == [("sample-id", ()), ("sample-id", ())]


@pytest.mark.parametrize("same_target", [True, False])
def test_validate_medium_layers_checks_liquid_volume_per_target(same_target):
    from culsma.domains.environment import EnvironmentValueError
    from culsma.domains.medium import LiquidMedium
    from culsma.pipeline.medium_boundary import encode_descriptor
    from culsma.runtime.environment_media import validate_medium_layers

    state = RuntimeState(artifacts={"material_state": {"containers": {"first": {}, "second": {}}}})
    outer = LiquidMedium(contents={"WATER": (100, "%")},
                         basis=CompositionBasis.VOLUME_FRACTION, volume=(500, "mL"))
    inner = LiquidMedium(contents={"WATER": (100, "%")},
                         basis=CompositionBasis.VOLUME_FRACTION, volume=(1, "L"))
    target = "first" if same_target else "second"
    gate = {"env_layers": [
        {"env": {"medium": encode_descriptor(outer)},
         "env_targets": [{"kind": "container_ref", "id": "first"}]},
        {"env": {"medium": encode_descriptor(inner)},
         "env_targets": [{"kind": "container_ref", "id": target}]},
    ]}
    if same_target:
        with pytest.raises(EnvironmentValueError, match="conflicting nested liquid medium"):
            validate_medium_layers(gate, state)
    else:
        validate_medium_layers(gate, state)
