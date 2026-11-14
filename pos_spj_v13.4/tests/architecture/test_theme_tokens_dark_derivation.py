"""SDLC-UI-004 — tokens semánticos completos y tema oscuro derivado de la marca.

* SUCCESS, WARNING, INFO y BORDER existen como tokens planos en los dos temas.
* El oscuro no reutiliza el color de marca crudo para PRIMARY/ACCENT/DANGER ni
  escribe hex a mano: se deriva de ``brand_palette.py`` con ``color_utils``.
* La paleta de gráficas depende del tema y sus series contrastan (≥ 3:1, regla
  de componente UI) contra la superficie oscura.
* La pantalla del cliente sigue el tema de la caja (decisión del responsable,
  2026-11-02) y los colores Qt fijos ceden su lugar a tokens.
"""

from __future__ import annotations

import ast
from itertools import combinations
from pathlib import Path
import re

import pytest

from frontend.desktop.themes.brand_palette import BrandColors
from frontend.desktop.themes.color_utils import AA_UI_COMPONENT, contrast_ratio, hex_to_rgb
from frontend.desktop.themes.semantic_colors import ChartPalette, Dark, Light, SemanticColors

ROOT = Path(__file__).resolve().parents[2]
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")


@pytest.mark.parametrize("theme", [Light, Dark], ids=["light", "dark"])
@pytest.mark.parametrize("flat,source", [
    ("SUCCESS", "SUCCESS_DEFAULT"), ("WARNING", "WARNING_DEFAULT"),
    ("INFO", "INFO_DEFAULT"), ("BORDER", "BORDER_DEFAULT"),
])
def test_flat_semantic_tokens_exist(theme, flat, source):
    assert getattr(theme, flat) == getattr(theme, source)


@pytest.mark.parametrize("flat", ["PRIMARY", "ACCENT", "DANGER"])
def test_dark_flat_tokens_are_tuned_not_raw_brand(flat):
    raw = {BrandColors.FOREST_GREEN, BrandColors.PREMIUM_GOLD, BrandColors.TRADITIONAL_RED}
    assert getattr(Dark, flat) not in raw
    assert getattr(Dark, flat) == getattr(Dark, f"{flat}_DEFAULT")


def test_dark_theme_has_no_hand_written_hex():
    tree = ast.parse((ROOT / "frontend/desktop/themes/semantic_colors.py").read_text(encoding="utf-8"))
    dark = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Dark")
    literals = [n.value for n in ast.walk(dark)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and _HEX.search(n.value)]
    assert literals == [], f"Dark escribe hex a mano en vez de derivarlos: {literals}"


def test_chart_palette_depends_on_theme():
    assert ChartPalette.for_theme("light").CATEGORICAL == ChartPalette.CATEGORICAL
    assert ChartPalette.for_theme("dark").CATEGORICAL != ChartPalette.CATEGORICAL


@pytest.mark.parametrize("background", ["SURFACE", "BACKGROUND"])
def test_dark_chart_series_contrast_with_dark_surface(background):
    palette = ChartPalette.for_theme("dark")
    surface = getattr(Dark, background)
    series = list(palette.CATEGORICAL) + list(palette.STATUS.values())
    weak = {c: round(contrast_ratio(c, surface), 2) for c in series
            if contrast_ratio(c, surface) < AA_UI_COMPONENT}
    assert not weak, f"series casi invisibles sobre Dark.{background}: {weak}"


def test_dark_chart_series_stay_distinct():
    palette = ChartPalette.for_theme("dark").CATEGORICAL
    assert len(palette) >= 6 and len(set(palette)) == len(palette)

    def distance(a, b):
        return sum((x - y) ** 2 for x, y in zip(hex_to_rgb(a), hex_to_rgb(b))) ** 0.5

    close = [(a, b) for a, b in combinations(palette, 2) if distance(a, b) < 40]
    assert not close, f"series demasiado parecidas: {close}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_chart_status_colors_come_from_semantic_tokens(theme):
    colors = SemanticColors.for_theme(theme)
    status = ChartPalette.for_theme(theme).STATUS
    assert status["success"] == colors.SUCCESS
    assert status["warning"] == colors.WARNING
    assert status["danger"] == colors.DANGER_DEFAULT
    assert status["info"] == colors.INFO


def test_chart_bridge_assigns_the_dark_palette_in_dark_theme():
    from backend.application.dto.charts.chart_data import ChartDataDTO, ChartSeriesDTO
    from frontend.desktop.charts.chart_bridge import build_chart_payload

    dto = ChartDataDTO(chart_id="c", chart_type="bar", title="t", subtitle=None, categories=("a",),
                       series=(ChartSeriesDTO("s", (1.0,)), ChartSeriesDTO("w", (2.0,), semantic="warning")))
    payload = build_chart_payload(dto, theme="dark")
    dark = ChartPalette.for_theme("dark")
    assert payload["palette"] == list(dark.CATEGORICAL)
    assert [s["color"] for s in payload["series"]] == [dark.CATEGORICAL[0], dark.STATUS["warning"]]


def _customer_display_rules(theme: str) -> str:
    from frontend.desktop.themes.qss_builder import build_qss
    return "\n".join(line for line in build_qss(theme).splitlines() if "customerDisplay" in line)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_customer_display_follows_the_register_theme(theme):
    colors = SemanticColors.for_theme(theme)
    rules = _customer_display_rules(theme)
    assert f"QWidget#customerDisplayWindow {{ background-color: {colors.BACKGROUND}; }}" in rules
    assert f"QWidget#customerDisplayWindow QLabel {{ color: {colors.TEXT_PRIMARY}; }}" in rules
    assert _customer_display_rules("light") != _customer_display_rules("dark")


@pytest.mark.parametrize("relative", [
    "frontend/desktop/components/entity_search_input.py",
    "frontend/desktop/components/search_selector.py",
    "frontend/desktop/modules/products/pages/categories_page.py",
])
def test_status_rows_do_not_use_fixed_qt_gray(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "Qt.gray" not in source


@pytest.mark.parametrize("theme", [Light, Dark], ids=["light", "dark"])
@pytest.mark.parametrize("fg,bg", [
    ("TEXT_PRIMARY", "BACKGROUND"),         # cart text
    ("TEXT_INVERSE", "PRIMARY_DEFAULT"),    # scale / points / status chips
    ("ACCENT_SUBTLE", "PRIMARY_DEFAULT"),   # thank-you points / confirmation
])
def test_customer_display_pairs_meet_aa_in_both_themes(theme, fg, bg):
    from frontend.desktop.themes.color_utils import AA_NORMAL_TEXT
    assert contrast_ratio(getattr(theme, fg), getattr(theme, bg)) >= AA_NORMAL_TEXT
