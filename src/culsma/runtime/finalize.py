"""Runtime finalization helpers."""

from __future__ import annotations

from culsma.common.diagnostics import Diagnostic
from culsma.runtime.report import LabReport
from culsma.runtime.session import RuntimeSession
from culsma.runtime.user_result import ReportBuilder


class RuntimeFinalizer:
    def __init__(self, report_builder: ReportBuilder | None = None) -> None:
        self.report_builder = report_builder or ReportBuilder()

    def finalize(self, session: RuntimeSession, *, aborted_due_to_error: bool) -> None:
        if aborted_due_to_error:
            for step in session.step_by_id.values():
                if session.state.step_status.get(step.step_id) != "pending":
                    continue
                session.record_skipped(step, "aborted_after_failure")
            session.emit_diagnostic(
                Diagnostic(
                    code="RT_ABORTED_AFTER_FAILURE",
                    message="Runtime aborted after first failed step (fail-fast mode)",
                    span=session.plan.span,
                    node_id=None,
                )
            )

        for step in session.step_by_id.values():
            if aborted_due_to_error:
                break
            status = session.state.step_status.get(step.step_id)
            if status != "pending":
                continue
            dep_status = [session.state.step_status.get(dep, "unknown") for dep in step.deps]
            if any(s in {"failed", "skipped"} for s in dep_status):
                session.record_skipped(step, "unsatisfied_dependency")
                session.emit_diagnostic(
                    Diagnostic(
                        code="RT_UNSATISFIED_DEPENDENCY",
                        message=f"Step '{step.step_id}' skipped due to unsatisfied dependency",
                        span=step.span,
                        node_id=step.step_id,
                    )
                )

        for step in session.step_by_id.values():
            if aborted_due_to_error:
                break
            if session.state.step_status.get(step.step_id) == "pending":
                session.state.step_status[step.step_id] = "failed"
                session.emit_diagnostic(
                    Diagnostic(
                        code="RT_STUCK_STEP",
                        message=f"Step '{step.step_id}' remained pending after scheduling",
                        span=step.span,
                        node_id=step.step_id,
                    )
                )
                session.event_log.emit("STEP_FAILED", step.step_id, payload={"reason": "stuck_pending"}, span=step.span)

        if session.protocol_output_recorder is not None:
            session.protocol_output_recorder.capture_all(session)

        session.diagnostics[:] = [
            d
            if d.node_id is None or d.node_id in session.step_by_id or d.code.startswith("PLAN_")
            else Diagnostic(
                code=d.code,
                message=d.message,
                span=d.span,
                severity=d.severity,
                node_id=None,
            )
            for d in session.diagnostics
        ]

    def build_report(self, session: RuntimeSession, *, ok: bool) -> LabReport:
        return self.report_builder.build(
            ok=ok,
            diagnostics=session.diagnostics,
            state=session.state,
            plan=session.plan,
            initial_material_state=session.initial_material_state,
            material_accounting=session.material_accounting,
        )
