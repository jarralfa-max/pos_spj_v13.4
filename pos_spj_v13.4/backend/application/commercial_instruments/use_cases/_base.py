"""Shared plumbing for Commercial Instruments use cases. Reuses LOY-1's
`LoyaltyAuthorizationPolicy`/`LoyaltyPermissions.COUPON_*` directly rather
than building a parallel authorization stack — coupons share the exact
same `GROWTH_ENGINE` permission surface as the rest of Fidelidad (master
prompt §6's own sidebar lists "Cupones" as one of Fidelidad's items), even
though the coupon ENTITIES live in their own bounded context
(`backend/domain/commercial_instruments/`) since a coupon is a commercial
instrument in its own right, not a loyalty-owned concept (§4).
"""

from __future__ import annotations

import json

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.commercial_instruments.events import commercial_instrument_event_payload


class _CommercialInstrumentBaseUseCase:
    def __init__(self, authorization: LoyaltyAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or LoyaltyAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = commercial_instrument_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
