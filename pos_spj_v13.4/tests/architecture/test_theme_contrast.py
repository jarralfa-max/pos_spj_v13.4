"""FASE DS-1 — WCAG AA contrast guardrails for the JUANIS semantic palette.

A color is never approved just for belonging to the brand: every text and UI
pair below must meet WCAG AA. Normal text ≥ 4.5:1, large/secondary text and UI
components ≥ 3.0:1.
"""

from __future__ import annotations

import pytest

from frontend.desktop.themes.color_utils import (
    AA_LARGE_TEXT,
    AA_NORMAL_TEXT,
    AA_UI_COMPONENT,
    contrast_ratio,
)
from frontend.desktop.themes.semantic_colors import Dark, Light

# (theme, fg_token, bg_token, threshold) — must all pass.
_NORMAL_TEXT_PAIRS = [
    ("light", "TEXT_PRIMARY", "BACKGROUND"),
    ("light", "TEXT_PRIMARY", "SURFACE"),
    ("light", "TEXT_SECONDARY", "SURFACE"),
    ("light", "TEXT_MUTED", "SURFACE"),
    ("light", "PRIMARY_DEFAULT", "SURFACE"),
    ("light", "DANGER_DEFAULT", "SURFACE"),
    ("light", "SUCCESS_DEFAULT", "SURFACE"),
    ("light", "WARNING_DEFAULT", "SURFACE"),
    ("light", "INFO_DEFAULT", "SURFACE"),
    ("light", "ACCENT_TEXT", "SURFACE"),
    ("light", "TEXT_PRIMARY", "ACCENT_DEFAULT"),   # dark text on a gold fill
    ("light", "DANGER_DEFAULT", "DANGER_SUBTLE"),
    ("light", "SUCCESS_DEFAULT", "SUCCESS_SUBTLE"),
    ("light", "WARNING_DEFAULT", "WARNING_SUBTLE"),
    ("light", "INFO_DEFAULT", "INFO_SUBTLE"),
    ("light", "TOOLTIP_TEXT", "TOOLTIP_BACKGROUND"),
    ("dark", "TEXT_PRIMARY", "BACKGROUND"),
    ("dark", "TEXT_PRIMARY", "SURFACE"),
    ("dark", "TEXT_SECONDARY", "SURFACE"),
    ("dark", "PRIMARY_DEFAULT", "SURFACE"),
    ("dark", "DANGER_DEFAULT", "SURFACE"),
    ("dark", "SUCCESS_DEFAULT", "SURFACE"),
    ("dark", "WARNING_DEFAULT", "SURFACE"),
    ("dark", "INFO_DEFAULT", "SURFACE"),
    ("dark", "ACCENT_TEXT", "SURFACE"),
    ("dark", "TOOLTIP_TEXT", "TOOLTIP_BACKGROUND"),
]

_LARGE_OR_UI_PAIRS = [
    ("light", "TEXT_MUTED", "SURFACE_MUTED"),
    ("light", "FOCUS_RING", "SURFACE"),
    ("light", "BORDER_STRONG", "SURFACE"),
    ("dark", "TEXT_MUTED", "SURFACE"),
    ("dark", "FOCUS_RING", "SURFACE"),
    ("dark", "BORDER_STRONG", "SURFACE"),
    ("dark", "TEXT_INVERSE", "ACCENT_DEFAULT"),
]

_THEMES = {"light": Light, "dark": Dark}


@pytest.mark.parametrize("theme,fg,bg", _NORMAL_TEXT_PAIRS)
def test_normal_text_pairs_meet_aa(theme, fg, bg):
    ns = _THEMES[theme]
    ratio = contrast_ratio(getattr(ns, fg), getattr(ns, bg))
    assert ratio >= AA_NORMAL_TEXT, (
        f"{theme}.{fg} on {theme}.{bg} = {ratio:.2f}:1 (< {AA_NORMAL_TEXT})")


@pytest.mark.parametrize("theme,fg,bg", _LARGE_OR_UI_PAIRS)
def test_large_and_ui_pairs_meet_aa(theme, fg, bg):
    ns = _THEMES[theme]
    ratio = contrast_ratio(getattr(ns, fg), getattr(ns, bg))
    assert ratio >= min(AA_LARGE_TEXT, AA_UI_COMPONENT), (
        f"{theme}.{fg} on {theme}.{bg} = {ratio:.2f}:1 (< {AA_LARGE_TEXT})")


def test_disabled_text_is_dimmer_than_primary_text():
    """Disabled must be legible-but-clearly-inactive: lower contrast than primary."""
    for ns in (Light, Dark):
        primary = contrast_ratio(ns.TEXT_PRIMARY, ns.SURFACE)
        disabled = contrast_ratio(ns.TEXT_DISABLED, ns.SURFACE)
        assert disabled < primary


def test_categorical_chart_colors_are_distinct():
    from frontend.desktop.themes.semantic_colors import ChartPalette
    assert len(set(ChartPalette.CATEGORICAL)) == len(ChartPalette.CATEGORICAL)
    assert len(ChartPalette.CATEGORICAL) >= 6
