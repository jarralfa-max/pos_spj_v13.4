# migrations/standalone/218_content_and_advertising_schema.py
"""SET-18 — Content and Advertising schema (Content, Campaigns,
Placements, Approval, Metrics).

Creates `display_content`, `content_campaigns`, `advertising_slots`,
`campaign_placements`, `content_impressions` — the `ContentCampaign`/
`AdvertisingSlot` pieces SET-0's own Customer Display audit had already
flagged as "build from scratch" and SET-17 explicitly deferred.

Depends on migration 217 (customer_displays/display_layouts) only
indirectly — no FK to those tables; `advertising_slots.mode` reuses the
same `CustomerDisplayMode` vocabulary but as a plain validated string,
matching how SET-17's own tables are structured.

DDL lives in backend/infrastructure/db/schema/customer_display_schema.py;
only this migration may call create_content_and_advertising_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_display_schema import (
    create_content_and_advertising_schema,
)

logger = logging.getLogger("spj.migrations.218")


def run(conn) -> None:
    create_content_and_advertising_schema(conn)
    conn.commit()
    logger.info(
        "218: display_content/content_campaigns/advertising_slots/campaign_placements/"
        "content_impressions schema created."
    )


up = run
