from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.framework.capability import CapabilityPolicy
from culsma.driver.framework.contracts import DriverContext
from culsma.driver.framework.driver import ProjectionDriver
from culsma.driver.framework.models import DriverProjection, MappingRecord
from culsma.driver.framework.registry import TranslatorRegistry
from culsma.pipeline.plan_nodes import PlanStep


class DemoBindingResolver:
    def bind(self, record: MappingRecord, context: DriverContext | None = None):
        return {
            "backend_name": "demo",
            "semantic_op": record.semantic_op,
            "driver_kind": context.driver_kind if context is not None else "demo",
        }


class DemoTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="demo",
            label="Demo projection",
            summary=f"Handle {record.semantic_op} in demo backend.",
            category="demo",
            binding=dict(binding),
            payload={"args": dict(record.semantic_args)},
        )


class DemoBackendEmitter:
    def emit(self, projection: DriverProjection) -> dict[str, object]:
        return {
            "demo_projection": {
                "label": projection.label,
                "summary": projection.summary,
            },
            "demo_binding": dict(projection.binding),
            "demo_payload": dict(projection.payload),
        }


class DemoReceiptNormalizer:
    def normalize(self, *, base_payload, emitted_payload):
        return {
            **dict(base_payload),
            **dict(emitted_payload),
            "receipt": {"status": "demo-ok"},
        }


@dataclass
class DemoDriver(ProjectionDriver):
    driver_kind: str = "demo"
    ok_code: str = "DRV_DEMO_OK"
    translator_registry: TranslatorRegistry = field(
        default_factory=lambda: TranslatorRegistry(
            translators={"Mutation": DemoTranslator()},
            default_translator=DemoTranslator(),
        )
    )
    binding_resolver: DemoBindingResolver = field(default_factory=DemoBindingResolver)
    backend_emitter: DemoBackendEmitter = field(default_factory=DemoBackendEmitter)
    receipt_normalizer: DemoReceiptNormalizer = field(default_factory=DemoReceiptNormalizer)


def test_projection_driver_allows_third_party_style_plugin_assembly():
    step = PlanStep(
        step_id="demo.1",
        op="Mutation",
        args={
            "target": {"kind": "IRIdentifier", "name": "dst"},
            "sources": [{"kind": "IRIdentifier", "name": "src"}],
        },
    )

    result = DemoDriver().execute(step)

    assert result.ok
    assert result.code == "DRV_DEMO_OK"
    assert result.payload["driver_kind"] == "demo"
    assert result.payload["demo_projection"]["label"] == "Demo projection"
    assert result.payload["demo_binding"]["backend_name"] == "demo"
    assert result.payload["demo_binding"]["driver_kind"] == "demo"
    assert result.payload["receipt"]["status"] == "demo-ok"


def test_projection_driver_check_uses_framework_capability_policy():
    step = PlanStep(
        step_id="demo.check.1",
        op="Mutation",
        args={},
        gate={"constraint": {"requirements": ["gentle"]}},
    )

    result = DemoDriver(supported_requirements={"aseptic"}).check(step)

    assert not result.ok
    assert result.code == "DRV_REQ_UNSUPPORTED"
    assert result.unsupported_requirements == ("gentle",)


def test_projection_driver_is_not_a_stub_driver_subclass():
    from culsma.driver.stub import StubDriver

    assert not issubclass(ProjectionDriver, StubDriver)
    assert isinstance(CapabilityPolicy(), CapabilityPolicy)


def test_mapping_record_extracts_program_descriptor_for_plugin_consumers():
    step = PlanStep(
        step_id="demo.2",
        op="phy",
        args={
            "sample": {"kind": "IRIdentifier", "name": "probe"},
            "program": {
                "kind": "IRCall",
                "name": "temperature_program",
                "args": [
                    {"name": "mode", "value": {"kind": "IRString", "value": "single"}},
                    {"name": "interval", "value": {"kind": "IRQuantity", "value": 5, "unit": "s"}},
                ],
            },
        },
    )

    record = DemoDriver().build_mapping_record(step)

    assert record.program_kind == "temperature_program"
    assert record.program_args["mode"]["value"] == "single"
    assert record.program_args["interval"]["unit"] == "s"


class ProgramSpecificTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="demo",
            label="Program-specific projection",
            summary=f"Handle {record.semantic_op} using {record.program_kind}.",
            category="demo",
            binding=dict(binding),
            payload={"program_kind": record.program_kind},
        )


@dataclass
class ProgramAwareDriver(ProjectionDriver):
    driver_kind: str = "demo"
    ok_code: str = "DRV_DEMO_OK"
    translator_registry: TranslatorRegistry = field(
        default_factory=lambda: TranslatorRegistry(
            translators={
                "phy": DemoTranslator(),
                ("phy", "temperature_program"): ProgramSpecificTranslator(),
            },
            default_translator=DemoTranslator(),
        )
    )
    binding_resolver: DemoBindingResolver = field(default_factory=DemoBindingResolver)
    backend_emitter: DemoBackendEmitter = field(default_factory=DemoBackendEmitter)
    receipt_normalizer: DemoReceiptNormalizer = field(default_factory=DemoReceiptNormalizer)


def test_registry_prefers_semantic_op_plus_program_kind_when_available():
    step = PlanStep(
        step_id="demo.3",
        op="phy",
        args={
            "sample": {"kind": "IRIdentifier", "name": "probe"},
            "program": {
                "kind": "IRCall",
                "name": "temperature_program",
                "args": [],
            },
        },
    )

    result = ProgramAwareDriver().execute(step)

    assert result.ok
    assert result.payload["demo_projection"]["label"] == "Program-specific projection"
    assert result.payload["demo_payload"]["program_kind"] == "temperature_program"
