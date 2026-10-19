"""SalesMarketingClient — Sales' integration point onto Document Output's
marketing-message capability (SET-13 cutover). Mirrors
`sales_receipt_client.py`'s shape: thin, delegates entirely to the real
domain policy/repository.

The context handed to `select_messages()`/`render_message()` is built from
ONLY real data already available at reprint time — `subtotal`, `total`,
`has_customer`, `points_balance`. No fabricated business metric (e.g. a
"goal_remaining" from a rewards catalog this repo doesn't have) is ever
invented — this constrains which `CampaignRule.metric`/template
placeholders an admin's campaign can usefully reference, which is honest,
not hidden.

A misconfigured campaign (a template referencing a context key that isn't
supplied) must never break a real print — that single message is skipped
and logged, not fatal.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.domain.document_output.enums import MarketingMessageCategory
from backend.domain.document_output.exceptions import DocumentInvalidValueError, MarketingClaimNotAllowedError
from backend.domain.document_output.policies.marketing_claim_validation_policy import select_messages
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)

logger = logging.getLogger(__name__)

_MAX_PER_CATEGORY = {
    MarketingMessageCategory.LOYALTY: 1, MarketingMessageCategory.FOMO: 2, MarketingMessageCategory.CTA: 1,
}


class SalesMarketingClient:
    def __init__(self, connection) -> None:
        self._connection = connection

    def select_ticket_messages(
        self, *, subtotal: Decimal, total: Decimal, has_customer: bool, points_balance: int | None,
        max_per_category: dict[str, int] | None = None,
    ) -> tuple[str, ...]:
        """`max_per_category` viene del bloque «Mensajes» del diseño del ticket
        (comparativa de tickets, 2026-10-16); antes era fijo en código."""
        context = {
            "subtotal": subtotal, "total": total, "has_customer": has_customer,
            "points_balance": Decimal(points_balance) if points_balance is not None else None,
        }
        limits = _MAX_PER_CATEGORY if max_per_category is None else {
            MarketingMessageCategory(k): int(v) for k, v in max_per_category.items()
            if k in MarketingMessageCategory.__members__}
        if not any(limits.values()):
            return ()           # el diseño no imprime mensajes: ni se consultan
        campaigns = SqliteMarketingCampaignRepository(self._connection).list_active()
        try:
            selected = select_messages(campaigns, context, max_per_category=limits)
        except (DocumentInvalidValueError, MarketingClaimNotAllowedError) as exc:
            # An individual campaign violating an invariant (e.g. a FOMO
            # campaign left without rules) must not suppress every other
            # campaign's message — degrade to none rather than propagate.
            logger.warning("Selección de mensajes de ticket omitida: %s", exc)
            return ()

        rendered: list[str] = []
        for campaign in selected:
            try:
                rendered.append(campaign.render_message(context))
            except (KeyError, DocumentInvalidValueError, MarketingClaimNotAllowedError) as exc:
                logger.warning("Campaña %s no se pudo renderizar en ticket: %s", campaign.code, exc)
        return tuple(rendered)
