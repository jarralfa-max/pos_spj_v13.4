"""FASE DS-8 — guardrails that keep the design system single-sourced.

These lock the standard for NEW frontend code (frontend/desktop/). They do not
police legacy modulos/ (that debt migrates module by module); they prevent the
new layer from fragmenting again.
"""

from __future__ import annotations

import re
import json
from pathlib import Path

import pytest

from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, scan_source

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "desktop"
THEMES = FRONTEND / "themes"
COMPONENTS = FRONTEND / "components"

# The five official JUANIS brand colors (any casing).
_BRAND_HEX = {"#18372B", "#FFFFFF", "#C6A15B", "#9D2927", "#252825", "#F8F8F5"}
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


def test_charts_render_via_html_js_not_native():
    """Charts go through ChartDataDTO → HTML+JS (ECharts). The DTO is color-free."""
    charts = FRONTEND / "charts"
    assert (charts / "templates" / "chart_base.html").exists()
    assert (charts / "renderers" / "echarts_renderer.js").exists()
    # The chart DTO must not embed color VALUES, HTML or JS (prose mentioning the
    # word "color" is fine; concrete presentation is not).
    dto_src = (REPO / "backend/application/dto/charts/chart_data.py").read_text(encoding="utf-8")
    assert not _HEX_RE.search(dto_src), "ChartDataDTO must not contain hex colors"
    for banned in ("rgb(", "rgba(", "<div", "setoption(", "echarts.init"):
        assert banned not in dto_src.lower(), f"ChartDataDTO must not contain {banned!r}"


def test_theme_layer_is_the_single_qss_source():
    """No component builds its own global stylesheet string via a QSS builder."""
    assert (THEMES / "qss_builder.py").exists()
    assert (THEMES / "theme_manager.py").exists()
    # components must not define their own build_qss
    for path in _py_files(COMPONENTS):
        assert "def build_qss" not in path.read_text(encoding="utf-8"), path.name


def test_desktop_visual_debt_does_not_grow():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    findings = scan_repository()
    new, _resolved = regressions(findings, baseline)
    details = [f"{item.path}:{item.line}: {item.rule}: {item.expression[:150]}"
               for item in findings if item.key in new]
    assert not new, "New visual violations (existing exact debt is not a file exemption):\n" + "\n".join(details)


@pytest.mark.parametrize(("source", "rule"), [
    ('button.setStyleSheet(style)', "inline_qss"),
    ('color = "#18372B"', "hardcoded_visual_hex"),
    ('color = "#ffffff"', "hardcoded_visual_hex"),
    ('from PyQt5.QtWidgets import QTableWidget as Grid\ntable = Grid()', "native_operational_table"),
    ('class LocalTable(QtWidgets.QTableWidget):\n    pass', "native_operational_table"),
    ('class KPICard(QWidget):\n    pass', "local_standard_component"),
    ('class SalesPageHeader(QWidget):\n    pass', "local_standard_component"),
    ('class LocalInput(QLineEdit):\n    def paintEvent(self, event):\n        pass', "local_visual_control"),
    ('class LocalButton(QPushButton):\n    def setup(self):\n        self.setFont(font)', "local_visual_control"),
    ('button = QPushButton("\\U0001f514 Notificaciones")', "unicode_icon_literal"),
    ('button = QPushButton()\nbutton.setFixedHeight(32)', "fixed_control_below_touch_target"),
    ('class SalesPage(QWidget):\n    pass', "screen_without_explicit_overflow"),
    ('class EditDialog(QDialog):\n    pass', "noncanonical_dialog"),
    ('class EditDialog(StandardDialog):\n    def setup(self):\n        self.setMinimumSize(1400, 900)', "dialog_geometry_exceeds_smallest_viewport"),
])
def test_ast_audit_detects_forbidden_module_patterns(source, rule):
    assert rule in {item.rule for item in scan_source(source, "frontend/desktop/modules/new/page.py")}


def test_ast_audit_accepts_canonical_composition_and_ignores_prose():
    source = '''
"""Do not call setStyleSheet('#18372B') or use a bell \\U0001f514 as an icon."""
from frontend.desktop.components import WorklistPage, PrimaryButton, StandardTable
class SalesPage(WorklistPage):
    def setup(self):
        self.table = StandardTable()
        self.button = PrimaryButton("Guardar")
'''
    assert not scan_source(source, "frontend/desktop/modules/new/page.py")


def test_ast_audit_accepts_explicit_scroll_and_keeps_web_colors_separate():
    source = 'class SalesPage(QWidget):\n    def setup(self):\n        self.viewport = PageViewport()'
    assert not scan_source(source, "frontend/desktop/modules/new/page.py")
    assert not scan_source('WEB_STYLE = "background: #18372B"', "frontend/desktop/charts/renderer.py")
    assert scan_source('widget.setStyleSheet("background: #18372B")', "frontend/desktop/charts/renderer.py")


def test_existing_file_debt_cannot_hide_new_expressions_or_duplicate_occurrences():
    path = "modulos/existing.py"
    old = scan_source('button.setStyleSheet("old")', path)[0]
    baseline = {"findings": [{"path": old.path, "rule": old.rule, "fingerprint": old.fingerprint, "count": 1}]}
    assert not regressions([old], baseline)[0]
    assert regressions([old, old], baseline)[0][old.key] == 1
    changed = scan_source('button.setStyleSheet("new")', path)
    assert regressions(changed, baseline)[0]
    assert regressions(scan_source('button.setStyleSheet("old")', "modulos/new.py"), baseline)[0]
