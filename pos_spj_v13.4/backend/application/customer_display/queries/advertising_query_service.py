"""AdvertisingQueryService — SET-18 cutover: resolves which
`ContentCampaign`(s) should actually be shown right now for a given
`CustomerDisplayMode`. Customer_display's own read-side projection, the
same role `CustomerDisplayQueryService` plays for Sales — but this one
belongs here, not under `sales/queries/`, because the data it projects
(Content/ContentCampaign/AdvertisingSlot/CampaignPlacement) is
customer_display's own domain, not Sales'.

**No domain policy exists for "is this campaign inside its scheduled
window"** — `ContentCampaign.create()` only validates `ends_at >=
starts_at`, nothing checks "now" against the pair. The window comparison
below is a plain, obviously-correct string comparison over ISO 8601
timestamps (sortable as strings) done at this application layer, not a
fabricated domain rule.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.application.customer_display.dto import ResolvedAdDTO
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.infrastructure.db.repositories.customer_display.advertising_slot_repository import (
    SqliteAdvertisingSlotRepository,
)
from backend.infrastructure.db.repositories.customer_display.campaign_placement_repository import (
    SqliteCampaignPlacementRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_repository import (
    SqliteContentRepository,
)
from backend.infrastructure.db.repositories.customer_display.display_media_repository import (
    SqliteDisplayMediaRepository,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AdvertisingQueryService:
    def __init__(self, connection, media_storage=None) -> None:
        self._conn = connection
        self._media = SqliteDisplayMediaRepository(connection)
        self._media_storage = media_storage
        self._slots = SqliteAdvertisingSlotRepository(connection)
        self._placements = SqliteCampaignPlacementRepository(connection)
        self._campaigns = SqliteContentCampaignRepository(connection)
        self._content = SqliteContentRepository(connection)

    def _media_path(self, content) -> str | None:
        """Ruta del archivo de un contenido IMAGE/VIDEO; `None` si no aplica o
        si el archivo desapareció de la carpeta (la pantalla lo dice)."""
        if content.content_type.value not in ("IMAGE", "VIDEO"):
            return None
        try:
            media = self._media.get(content.body)
        except sqlite3.OperationalError:  # base sin display_media (anterior a la 313)
            return None
        if media is None:
            return None
        if self._media_storage is None:
            from backend.infrastructure.customer_display.media_storage import DisplayMediaStorage
            self._media_storage = DisplayMediaStorage()
        path = self._media_storage.path_for(media.stored_name)
        return str(path) if path.is_file() else None

    def resolve_active_ads(self, mode: CustomerDisplayMode | str) -> tuple[ResolvedAdDTO, ...]:
        mode = CustomerDisplayMode(mode)
        now = _now_iso()
        resolved: list[ResolvedAdDTO] = []
        for slot in self._slots.list_by_mode(mode):
            if not slot.active:
                continue
            placement = self._placements.get_active_for_slot(slot.id)
            if placement is None:
                continue
            campaign = self._campaigns.get(placement.campaign_id)
            if campaign is None or not campaign.is_active():
                continue
            if campaign.starts_at and now < campaign.starts_at:
                continue
            if campaign.ends_at and now > campaign.ends_at:
                continue
            content = self._content.get(campaign.content_id)
            if content is None or not content.active:
                continue
            resolved.append(ResolvedAdDTO(
                placement_id=placement.id, campaign_id=campaign.id, content_id=content.id,
                title=content.title, content_type=content.content_type.value, body=content.body,
                duration_seconds=content.duration_seconds,
                media_path=self._media_path(content),
            ))
        return tuple(resolved)
