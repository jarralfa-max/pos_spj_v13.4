"""Appearance schema — SET-22.

DDL lives only here; only migration 222 may call
`create_appearance_schema`. Backs `backend/domain/appearance/` (SET-22):
`themes` mirrors `Theme`, `design_tokens` mirrors `DesignToken`,
`density_profiles` mirrors `DensityProfile`, `appearance_preferences`
mirrors `AppearancePreference`.

No legacy table-name collision — the legacy theme/density preferences
live as flat keys (`'tema'`, `'ui_theme'`, `'ui_density'`, `'ui_font_size'`,
`'ui_icon_size'`) inside the generic `configuraciones(clave, valor)`
table, not in dedicated tables. This schema is born-clean and UUIDv7 from
the start, with no relationship to `configuraciones`.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_THEME_MODES = "'LIGHT','DARK'"
_DENSITY_LEVELS = "'COMPACT','NORMAL','COMFORTABLE'"
_TOKEN_CATEGORIES = (
    "'COLOR','SPACING','TYPOGRAPHY','RADIUS','BORDER','ELEVATION','ICON_SIZE','CONTROL_HEIGHT'"
)
_SCOPE_TYPES = "'GLOBAL','BRANCH','USER'"

_THEMES_DDL = f"""
    CREATE TABLE IF NOT EXISTS themes (
        id            TEXT PRIMARY KEY CHECK({_uuid('id')}),
        code          TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name          TEXT NOT NULL CHECK(trim(name)<>''),
        mode          TEXT NOT NULL CHECK(mode IN ({_THEME_MODES})),
        active        INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        is_default    INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
"""

_DESIGN_TOKENS_DDL = f"""
    CREATE TABLE IF NOT EXISTS design_tokens (
        id            TEXT PRIMARY KEY CHECK({_uuid('id')}),
        theme_id      TEXT REFERENCES themes(id) CHECK(theme_id IS NULL OR ({_uuid('theme_id')})),
        token_key     TEXT NOT NULL CHECK(trim(token_key)<>''),
        category      TEXT NOT NULL CHECK(category IN ({_TOKEN_CATEGORIES})),
        token_value   TEXT NOT NULL CHECK(trim(token_value)<>''),
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
"""

_DENSITY_PROFILES_DDL = f"""
    CREATE TABLE IF NOT EXISTS density_profiles (
        id                  TEXT PRIMARY KEY CHECK({_uuid('id')}),
        level               TEXT NOT NULL UNIQUE CHECK(level IN ({_DENSITY_LEVELS})),
        name                TEXT NOT NULL CHECK(trim(name)<>''),
        scale_factor        TEXT NOT NULL CHECK(trim(scale_factor)<>''),
        control_height_px   INTEGER NOT NULL CHECK(control_height_px > 0),
        touch_target_px     INTEGER NOT NULL CHECK(touch_target_px > 0),
        spacing_unit_px     INTEGER NOT NULL CHECK(spacing_unit_px > 0),
        active              INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    )
"""

_APPEARANCE_PREFERENCES_DDL = f"""
    CREATE TABLE IF NOT EXISTS appearance_preferences (
        id               TEXT PRIMARY KEY CHECK({_uuid('id')}),
        scope_type       TEXT NOT NULL CHECK(scope_type IN ({_SCOPE_TYPES})),
        scope_id         TEXT,
        theme_id         TEXT NOT NULL REFERENCES themes(id) CHECK({_uuid('theme_id')}),
        density_level    TEXT NOT NULL CHECK(density_level IN ({_DENSITY_LEVELS})),
        active           INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_themes_active ON themes(active)",
    # At most one default theme system-wide: every row that matches the
    # WHERE clause has is_default=1, so uniqueness on that single column
    # blocks a second row from ever satisfying the filter (same partial-
    # unique-index idiom as ux_ff_rules_scope_active, applied here to a
    # singleton instead of a per-scope constraint).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_themes_single_default ON themes(is_default) WHERE is_default=1",
    "CREATE INDEX IF NOT EXISTS idx_design_tokens_theme ON design_tokens(theme_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_design_tokens_scope "
    "ON design_tokens(COALESCE(theme_id,''), token_key)",
    "CREATE INDEX IF NOT EXISTS idx_density_profiles_active ON density_profiles(active)",
    "CREATE INDEX IF NOT EXISTS idx_appearance_preferences_theme ON appearance_preferences(theme_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_appearance_preferences_scope_active "
    "ON appearance_preferences(scope_type, COALESCE(scope_id,'')) WHERE active=1",
)


def create_appearance_schema(conn) -> None:
    conn.execute(_THEMES_DDL)
    conn.execute(_DESIGN_TOKENS_DDL)
    conn.execute(_DENSITY_PROFILES_DDL)
    conn.execute(_APPEARANCE_PREFERENCES_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
