"""Shared plumbing for Sweepstakes use cases. Reuses LOY-1's
`LoyaltyAuthorizationPolicy`/`LoyaltyPermissions.SWEEPSTAKES_*` directly
rather than building a parallel authorization stack — sweepstakes share the
same `GROWTH_ENGINE` permission/nav surface as the rest of Fidelidad, even
though the SWEEPSTAKES ENTITIES live in their own bounded context
(`backend/domain/sweepstakes/`), same convention as
`backend/application/commercial_instruments/use_cases/_base.py`."""

from __future__ import annotations

import json

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.sweepstakes.events import sweepstakes_event_payload


class _SweepstakesBaseUseCase:
    def __init__(self, authorization: LoyaltyAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or LoyaltyAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = sweepstakes_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
