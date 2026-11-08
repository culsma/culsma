"""Access guarantees owned by with-sep, independent of ordinary environments."""
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.contents_state import invalidate_contents_state
from culsma.runtime.material.refs import resolve_structured_ref


def scopes(step: PlanStep) -> list[dict[str, Any]]:
    return (step.gate or {}).get('separation_scopes', [])


def bind_result(step: PlanStep, state: dict[str, Any]) -> None:
    owner = (step.gate or {}).get('separation_entry')
    for source, record in state.get('contents_states', {}).items():
        if record.get('step_id') != step.step_id:
            continue
        result_owner = owner
        if result_owner is None:
            result_owner = next((scope['scope_id'] for scope in reversed(scopes(step))
                                 if resolve_structured_ref(state, scope['sample'], create_if_identifier=False) == source), None)
        if result_owner is not None:
            record['owner_separation_scope'] = result_owner
            contract = record.get('preservation_contract')
            if isinstance(contract, dict):
                # View lifetime and the provider of a retaining field are
                # independent. A non-magnetic scope must not replace an
                # explicitly authored magnetic environment.
                provider = next((scope['scope_id'] for scope in reversed(scopes(step))
                                 if scope.get('program', {}).get('name') == 'magnetic_program'
                                 and resolve_structured_ref(state, scope['sample'], create_if_identifier=False) == source), None)
                if provider is not None:
                    contract['separation_scope'] = provider


def expire(state: dict[str, Any], *, active: set[str] | None = None,
           ended: set[str] | None = None) -> list[str]:
    expired = []
    for source, record in state.get('contents_states', {}).items():
        owner = record.get('owner_separation_scope')
        if owner is not None and record.get('valid') and (
            owner in (ended or set()) or (active is not None and owner not in active)
        ):
            invalidate_contents_state(state, source, reason='separation_scope_ended')
            expired.append(source)
    return expired
