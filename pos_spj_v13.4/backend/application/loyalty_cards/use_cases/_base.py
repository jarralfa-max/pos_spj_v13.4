"""Shared plumbing for Loyalty Cards use cases. Mirrors
backend/application/sweepstakes/use_cases/_base.py exactly, using LOY-1's
own `LoyaltyCardsAuthorizationPolicy` (this bounded context's own policy,
NOT `LoyaltyAuthorizationPolicy` — Loyalty Cards has its own
`TARJETAS_FIDELIDAD` permission surface and segregation-of-duties roles,
§30)."""

from __future__ import annotations

import json

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.domain.loyalty_cards.events import loyalty_card_event_payload


class _LoyaltyCardsBaseUseCase:
    def __init__(self, authorization: LoyaltyCardsAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or LoyaltyCardsAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = loyalty_card_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
