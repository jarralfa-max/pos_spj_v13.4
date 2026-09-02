"""CampaignPlacementPolicy — SET-18 "Placements" gated by "Approval":
only an ACTIVE `ContentCampaign` (submitted, approved, and activated —
see `entities/content_campaign.py`'s status machine) may ever be assigned
to an `AdvertisingSlot`. Unapproved/unreviewed content reaching the
customer-facing screen is exactly the risk the approval workflow exists
to prevent.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.entities.campaign_placement import CampaignPlacement
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.exceptions import CampaignPlacementNotAllowedError


def assign_placement(
    campaign: ContentCampaign, slot: AdvertisingSlot, *, assigned_by_user_id: str | None = None,
) -> CampaignPlacement:
    if not campaign.is_active():
        raise CampaignPlacementNotAllowedError(
            f"La campaña {campaign.name!r} no está ACTIVE (estado actual: {campaign.status.value}) "
            "— no puede asignarse a un slot"
        )
    if not slot.active:
        raise CampaignPlacementNotAllowedError(f"El slot {slot.code!r} no está activo")
    return CampaignPlacement.assign(
        campaign_id=campaign.id, slot_id=slot.id, assigned_by_user_id=assigned_by_user_id,
    )
