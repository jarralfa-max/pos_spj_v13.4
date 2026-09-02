"""TokenResolutionPolicy — SET-22 "Tokens": merges GLOBAL design tokens
with a theme's own overrides into the flat `{token_key: token_value}` map
a QSS/style builder actually needs — generalizing
`modulos/qss_builder.build_themes()`, which reads hardcoded Python
constants from `modulos/design_tokens.py` with no override mechanism at
all.

A theme-scoped token (`theme_id == theme_id`) always wins over a GLOBAL
token (`theme_id is None`) with the same `token_key` — last-wins,
theme-specific overrides the shared default. Tokens for a *different*
theme are ignored entirely.
"""

from __future__ import annotations

from backend.domain.appearance.entities.design_token import DesignToken


def resolve_tokens_for_theme(tokens: list[DesignToken], theme_id: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for token in tokens:
        if token.theme_id is None:
            resolved[token.token_key] = token.token_value
    for token in tokens:
        if token.theme_id == theme_id:
            resolved[token.token_key] = token.token_value
    return resolved
