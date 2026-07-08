"""Protocol output capture helpers for runtime."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.plan_nodes import PlanStep, ProtocolPlan
from culsma.runtime.session import RuntimeSession
from culsma.runtime.values import UNRESOLVED


class ProtocolOutputRecorder:
    def capture_if_ready(self, step: PlanStep, session: RuntimeSession) -> None:
        protocol = session.protocol_plan_by_last_step_id.get(step.step_id)
        if protocol is None:
            return
        self.capture_protocol(protocol, session)

    def capture_all(self, session: RuntimeSession) -> None:
        outputs = session.state.artifacts.setdefault("protocol_outputs", {})
        if not isinstance(outputs, dict):
            return
        for protocol in session.plan.plans:
            output_name = protocol.output_name or protocol.protocol_name
            if output_name in outputs:
                continue
            self.capture_protocol(protocol, session)

    def capture_protocol(self, protocol: ProtocolPlan, session: RuntimeSession) -> None:
        outputs = session.state.artifacts.setdefault("protocol_outputs", {})
        if not isinstance(outputs, dict):
            return

        output_name = protocol.output_name or protocol.protocol_name
        payload: dict[str, Any] = {
            "protocol_id": protocol.protocol_id,
            "protocol_name": protocol.protocol_name,
            "returns": list(protocol.returns),
        }
        if protocol.entry_kind != "protocol":
            payload["entry_kind"] = protocol.entry_kind
        resolver = session.value_resolver
        if protocol.return_bindings:
            bindings: dict[str, Any] = {}
            for name, expr in protocol.return_bindings.items():
                value = resolver.eval_protocol_output_expr(expr, session.state)
                bindings[name] = None if value is UNRESOLVED else resolver.protocol_output_serialize(value)
            payload["bindings"] = bindings
        elif protocol.return_value is not None:
            value = resolver.eval_protocol_output_expr(protocol.return_value, session.state)
            payload["value"] = None if value is UNRESOLVED else resolver.protocol_output_serialize(value)
        outputs[output_name] = payload
