"""MarketingClaimValidationPolicy — SET-13 "FOMO policy": the
"responsible FOMO" rule. Every message the legacy
`core/tickets/ticket_message_engine.py::TicketMessageEngine` ever printed
was derived from real, current business state — an actual points
balance, an actual promo expiry date, an actual goal-remaining count —
never a fabricated "buy now!" with nothing behind it. `assert_responsible_claim`
encodes that same discipline as a domain rule: a FOMO-category
`MarketingCampaign` must be backed by at least one `CampaignRule`, so it
can only ever print when a real, checkable condition is true, never
unconditionally.

`select_messages` generalizes the legacy engine's own frequency cap
(`max_fomo=2`, applied only to FOMO messages) to all three categories —
a real product safeguard, not decoration: printing every eligible
loyalty/FOMO/CTA message every time would make the ticket unreadable and
undercut the very persuasion it's meant to add.
"""

from __future__ import annotations

from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.enums import MarketingMessageCategory
from backend.domain.document_output.exceptions import MarketingClaimNotAllowedError


def assert_responsible_claim(campaign: MarketingCampaign) -> None:
    if campaign.category is MarketingMessageCategory.FOMO and not campaign.rules:
        raise MarketingClaimNotAllowedError(
            f"La campaña FOMO {campaign.code!r} no tiene reglas — un mensaje de urgencia/escasez "
            "debe estar respaldado por al menos una condición real y verificable (§ FOMO responsable)"
        )


def select_messages(
    campaigns: list[MarketingCampaign], context: dict, *,
    max_per_category: dict[MarketingMessageCategory, int] | None = None,
) -> tuple[MarketingCampaign, ...]:
    """Matching campaigns only, validated for responsible FOMO, most
    urgent (highest priority) first per category, capped per category."""
    limits = dict(max_per_category or {})
    by_category: dict[MarketingMessageCategory, list[MarketingCampaign]] = {
        category: [] for category in MarketingMessageCategory
    }
    for campaign in campaigns:
        if not campaign.matches(context):
            continue
        assert_responsible_claim(campaign)
        by_category[campaign.category].append(campaign)

    selected: list[MarketingCampaign] = []
    for category, matched in by_category.items():
        ordered = sorted(matched, key=lambda c: c.priority, reverse=True)
        limit = limits.get(category)
        selected.extend(ordered if limit is None else ordered[:limit])
    return tuple(selected)
