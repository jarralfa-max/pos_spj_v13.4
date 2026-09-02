# migrations/standalone/215_marketing_campaigns_schema.py
"""SET-13 — Marketing Campaigns schema (Marketing en tickets: Campaigns,
Rules, FOMO policy, Loyalty summary).

Creates `marketing_campaigns` (Campaigns + Rules, §"FOMO responsable").
`CampaignRule`/`LoyaltySummary` are pure domain value objects with no
schema of their own — a campaign's rules are stored inline as
`rules_json` on its own row, and loyalty summary data is read live from
the loyalty bounded context at render time, never persisted here.

DDL lives in backend/infrastructure/db/schema/document_output_schema.py;
only this migration may call create_marketing_campaigns_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.document_output_schema import create_marketing_campaigns_schema

logger = logging.getLogger("spj.migrations.215")


def run(conn) -> None:
    create_marketing_campaigns_schema(conn)
    conn.commit()
    logger.info("215: marketing_campaigns schema created.")


up = run
