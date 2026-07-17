"""FASE DS-8 — guardrails that keep the design system single-sourced.

These lock the standard for NEW frontend code (frontend/desktop/). They do not
police legacy modulos/ (that debt migrates module by module); they prevent the
new layer from fragmenting again.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "desktop"
THEMES = FRONTEND / "themes"
COMPONENTS = FRONTEND / "components"

# The five official JUANIS brand colors (any casing).
_BRAND_HEX = {"#1F3B2E", "#A52E2A", "#C7A254", "#F2E6CF", "#6B4A2E"}
_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
_SETSTYLE_RE = re.compile(r"\.setStyleSheet\s*\(\s*[^)\s]")  # non-empty argument
_CHART_RE = re.compile(r"\bQtChart\b|\bQChart\b|matplotlib|pyqtgraph")


def _py_files(root: Path):
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def test_brand_colors_only_in_theme_layer():
    """The JUANIS brand hex values may appear only under themes/ (+ charts/)."""
    offenders = []
    allowed = {THEMES}
    charts = FRONTEND / "charts"
    if charts.exists():
        allowed.add(charts)
    for path in _py_files(FRONTEND):
        if any(str(path).startswith(str(a)) for a in allowed):
            continue
        found = {h.upper() for h in _HEX_RE.findall(path.read_text(encoding="utf-8"))}
        if found & _BRAND_HEX:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Brand hex outside theme layer: {offenders}"


def test_no_hardcoded_hex_in_components():
    """Canonical components must pull color from tokens/QSS, not inline hex."""
    offenders = []
    for path in _py_files(COMPONENTS):
        hits = _HEX_RE.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders.append(f"{path.relative_to(REPO)}: {hits[:3]}")
    assert not offenders, "Hardcoded hex in components:\n" + "\n".join(offenders)


def test_no_inline_stylesheets_in_components():
    offenders = []
    for path in _py_files(COMPONENTS):
        if _SETSTYLE_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Inline setStyleSheet in components: {offenders}"


def test_no_native_pyqt_charts_in_frontend():
    offenders = []
    for path in _py_files(FRONTEND):
        if _CHART_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Native/py chart libs in frontend: {offenders}"


def test_time_input_builds_on_qtimeedit_not_qlineedit():
    src = (COMPONENTS / "time_input.py").read_text(encoding="utf-8")
    assert "class TimeInput(QTimeEdit)" in src
    assert "QLineEdit(" not in src  # never instantiate a free-text field
    assert "def time_text" in src and "def set_time_text" in src


def test_theme_layer_is_the_single_qss_source():
    """No component builds its own global stylesheet string via a QSS builder."""
    assert (THEMES / "qss_builder.py").exists()
    assert (THEMES / "theme_manager.py").exists()
    # components must not define their own build_qss
    for path in _py_files(COMPONENTS):
        assert "def build_qss" not in path.read_text(encoding="utf-8"), path.name
