"""Shared plumbing for Fidelidad/Loyalty use cases — authorization
injection and outbox event emission. Mirrors
backend/application/sales/use_cases/_base.py exactly.

Same open gap as Sales' own equivalent: no call to
`record_loyalty_audit_entry` from here (LOY-1) — it needs a `container`, not
a bare `connection`, threading it through every use case is a real API-shape
decision deferred to whichever future phase wires these into a real UI.
Documented, not silently skipped.
"""

from __future__ import annotations

import json

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.loyalty.events import loyalty_event_payload


class _LoyaltyBaseUseCase:
    def __init__(self, authorization: LoyaltyAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or LoyaltyAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = loyalty_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
