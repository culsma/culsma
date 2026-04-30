"""Shared execution skeleton for projection-based drivers."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.base import DriverCapabilityResult, DriverResult
from culsma.pipeline.plan_nodes import PlanStep

from .capability import CapabilityPolicy
from .contracts import BackendEmitter, BindingResolver, DriverContext, ReceiptNormalizer
from .mapping_core import normalize_step
from .models import DriverProjection, MappingRecord
from .registry import TranslatorRegistry


@dataclass
class ProjectionDriver:
    """Shared skeleton for drivers that project canonical steps into backend expressions."""

    driver_kind: str = "generic"
    ok_code: str = "DRV_GENERIC_OK"
    fail_ops: set[str] = field(default_factory=set)
    non_fatal_fail_ops: set[str] = field(default_factory=set)
    op_payloads: dict[str, dict[str, object]] = field(default_factory=dict)
    step_payloads: dict[str, dict[str, object]] = field(default_factory=dict)
    supported_requirements: set[str] | None = None
    supported_constraint_option_keys: set[str] | None = None
    capability_policy: CapabilityPolicy | None = None
    translator_registry: TranslatorRegistry | None = None
    binding_resolver: BindingResolver | None = None
    backend_emitter: BackendEmitter | None = None
    receipt_normalizer: ReceiptNormalizer | None = None

    def check(self, step: PlanStep) -> DriverCapabilityResult:
        return self._capability_policy().evaluate(step)

    def execute(self, step: PlanStep) -> DriverResult:
        base_result = self._base_execute(step)
        payload = dict(base_result.payload)
        payload["driver_kind"] = self.driver_kind
        if not base_result.ok:
            return DriverResult(ok=False, code=base_result.code, payload=payload)

        if self.translator_registry is None or self.binding_resolver is None or self.backend_emitter is None or self.receipt_normalizer is None:
            return DriverResult(ok=True, code=self.ok_code, payload=payload)

        projection = self.project_step(step)
        emitted_payload = self.backend_emitter.emit(projection)
        normalized_payload = self.receipt_normalizer.normalize(
            base_payload=payload,
            emitted_payload=emitted_payload,
        )
        return DriverResult(ok=True, code=self.ok_code, payload=normalized_payload)

    def project_step(self, step: PlanStep) -> DriverProjection:
        if self.translator_registry is None or self.binding_resolver is None:
            raise LookupError("Projection pipeline is not configured")
        record = self.build_mapping_record(step)
        context = self.build_context(step, record)
        binding = self.binding_resolver.bind(record, context=context)
        translator = self.select_translator(record)
        return translator.translate(record, binding)

    def build_mapping_record(self, step: PlanStep) -> MappingRecord:
        return normalize_step(step)

    def build_context(self, step: PlanStep, record: MappingRecord) -> DriverContext:
        del step, record
        return DriverContext(driver_kind=self.driver_kind)

    def select_translator(self, record: MappingRecord):
        if self.translator_registry is None:
            raise LookupError("Translator registry is not configured")
        return self.translator_registry.select(record)

    def _capability_policy(self) -> CapabilityPolicy:
        if self.capability_policy is not None:
            return self.capability_policy
        return CapabilityPolicy(
            supported_requirements=self.supported_requirements,
            supported_constraint_option_keys=self.supported_constraint_option_keys,
        )

    def _base_execute(self, step: PlanStep) -> DriverResult:
        if step.op in self.non_fatal_fail_ops:
            return DriverResult(
                ok=False,
                code="DRV_SIMULATED_NON_FATAL_FAILURE",
                payload={"step_id": step.step_id, "op": step.op, "error_severity": "non_fatal"},
            )
        if step.op in self.fail_ops:
            return DriverResult(
                ok=False,
                code="DRV_SIMULATED_FAILURE",
                payload={"step_id": step.step_id, "op": step.op, "error_severity": "fatal"},
            )
        payload = {"step_id": step.step_id, "op": step.op}
        op_payload = self.op_payloads.get(step.op)
        if isinstance(op_payload, dict):
            payload.update(op_payload)
        step_payload = self.step_payloads.get(step.step_id)
        if isinstance(step_payload, dict):
            payload.update(step_payload)
        return DriverResult(ok=True, code="DRV_OK", payload=payload)
