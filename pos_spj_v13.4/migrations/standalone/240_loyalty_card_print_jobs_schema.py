# migrations/standalone/240_loyalty_card_print_jobs_schema.py
"""Loyalty Card print jobs (LOY-22, §50-51). Re-invokes
`create_loyalty_cards_schema()` (idempotent), same schema-extension pattern
as migrations 237-239.

`LoyaltyCardPrintJob` lives in its own schema rather than reusing
`document_output.print_jobs` — that table's `template_version_id` column
carries a real, enforced FK to `document_template_versions(id)`, which a
`LoyaltyCardTemplateVersion` id cannot satisfy (see
`backend/domain/loyalty_cards/entities/loyalty_card_print_job.py`'s own
docstring for the full story).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.240")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("240: loyalty_card_print_jobs schema ensured.")


up = run
