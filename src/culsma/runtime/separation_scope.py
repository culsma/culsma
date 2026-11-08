"""Record scope cleanup for non-material control flow and replay."""
from culsma.runtime.material.separation_scope import expire
from culsma.runtime.session import RuntimeSession


def expire_session_scopes(session: RuntimeSession, *, step_id: str,
                          active: set[str] | None = None, ended: set[str] | None = None) -> None:
    expired = expire(session.state.artifacts.get('material_state', {}), active=active, ended=ended)
    if expired:
        session.event_log.emit('SEPARATION_SCOPES_EXPIRED', step_id, payload={'sources': expired})
