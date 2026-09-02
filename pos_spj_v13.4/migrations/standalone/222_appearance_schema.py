# migrations/standalone/222_appearance_schema.py
"""SET-22 — Appearance schema (Themes, Tokens, Light/dark, Density).

Creates `themes`, `design_tokens`, `density_profiles`,
`appearance_preferences` — a born-clean, UUIDv7-native, scoped
(GLOBAL/BRANCH/USER) replacement concept for the legacy flat
`configuraciones` keys `'tema'`/`'ui_theme'`/`'ui_density'`/
`'ui_font_size'`/`'ui_icon_size'` (`ui/themes/theme_engine.py` and
`core/services/theme_service.py`), which store exactly one unscoped
theme/density pair with raw SQL against a generic `(clave, valor)` table.

DDL lives in backend/infrastructure/db/schema/appearance_schema.py; only
this migration may call create_appearance_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.appearance_schema import create_appearance_schema

logger = logging.getLogger("spj.migrations.222")


def run(conn) -> None:
    create_appearance_schema(conn)
    conn.commit()
    logger.info("222: themes/design_tokens/density_profiles/appearance_preferences schema created.")


up = run
