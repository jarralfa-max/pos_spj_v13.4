"""
tests/purchases/test_fase4_dark_light_theme.py
───────────────────────────────────────────────
FASE 4 — Dark/Light theme: sin fondos hardcodeados en compras_pro.py.

Verifica que NINGÚN widget activo (renderizado) use:
- Colors.NEUTRAL.SLATE_50 como background
- background:white / background: white
- Colors.NEUTRAL.WHITE como background de widget

Excepciones documentadas:
- SLATE_500 para texto (caption, label) → PERMITIDO
- SLATE_100 en badges pequeños → PERMITIDO
- HTML de impresión (_generar_html_compra) → EXEMPT: usa literales #f8fafc/#ffffff
  porque CSS de tema no se aplica a HTML enviado a QPrinter
- Dead code `_build_provider_sidebar` eliminado en FASE 10; colores no renderizados removidos

No instancia PyQt5.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import re
import pytest


def _source() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, "modulos", "compras_pro.py"), encoding="utf-8").read()


def _method_src(method_name: str) -> str | None:
    src = _source()
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ModuloComprasPro":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


def _has_slate50_as_background(method_src: str) -> list[str]:
    """Returns list of offending lines where SLATE_50 (exact) appears as background.
    SLATE_500, SLATE_100, etc. are NOT matched — only the literal token SLATE_50.
    A line counts as an offense only if 'background' appears AND it's not purely a text-color rule.
    """
    offenses = []
    for line in method_src.splitlines():
        stripped = line.strip()
        # Match SLATE_50 as exact token (not SLATE_500, SLATE_100, etc.)
        if not re.search(r'\bSLATE_50\b', stripped):
            continue
        if "background" not in stripped:
            continue
        # If the ONLY thing on the line is color:...SLATE_50;background:transparent — skip
        # (it's a text color declaration that happens to also set background:transparent)
        if "background:transparent" in stripped or "background: transparent" in stripped:
            continue
        # If SLATE_50 appears after 'color:' and before 'background', it's a text color
        before_bg = stripped.split("background")[0]
        if "color:" in before_bg[-50:] and "background" not in before_bg[-50:]:
            continue
        offenses.append(stripped)
    return offenses


def _has_background_white(method_src: str) -> list[str]:
    """Returns lines with background:white or background: white."""
    return [
        line.strip()
        for line in method_src.splitlines()
        if re.search(r'background\s*:\s*white\b', line, re.IGNORECASE)
    ]


def _has_neutral_white_background(method_src: str) -> list[str]:
    """Returns lines where Colors.NEUTRAL.WHITE is used as background."""
    return [
        line.strip()
        for line in method_src.splitlines()
        if "NEUTRAL.WHITE" in line and "background" in line
    ]


# ── Historial tab — previously violated ─────────────────────────────────────

class TestHistorialTabTheme:
    """Tab Historial no debe tener SLATE_50 como background de widgets."""

    def test_hist_timeline_bar_no_slate50(self):
        src = _method_src("_build_tab_historial")
        assert src is not None
        offenses = _has_slate50_as_background(src)
        assert not offenses, (
            f"_build_tab_historial usa SLATE_50 como background: {offenses}. "
            f"Usar background:transparent para compatibilidad con dark theme."
        )

    def test_hist_timeline_bar_uses_transparent(self):
        src = _method_src("_build_tab_historial")
        assert src is not None
        # After fix: _hist_timeline_bar should use transparent
        assert "background:transparent" in src or "background: transparent" in src, (
            "_hist_timeline_bar debe usar background:transparent (no SLATE_50)"
        )

    def test_hist_timeline_bar_no_background_white(self):
        src = _method_src("_build_tab_historial")
        assert src is not None
        offenses = _has_background_white(src)
        assert not offenses, f"background:white en _build_tab_historial: {offenses}"


class TestHistKPISidebarTheme:
    """KPI sidebar del historial no debe usar SLATE_50 como background."""

    def test_hist_kpi_sidebar_no_slate50_background(self):
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        offenses = _has_slate50_as_background(src)
        assert not offenses, (
            f"_build_hist_kpi_sidebar usa SLATE_50 como background: {offenses}"
        )

    def test_hist_kpi_sidebar_uses_transparent_background(self):
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        assert "background:transparent" in src or "background: transparent" in src, (
            "_build_hist_kpi_sidebar debe usar background:transparent en el QFrame principal"
        )


# ── QSplitter handle ─────────────────────────────────────────────────────────

class TestSplitterHandleVisibility:
    """El handle del QSplitter debe ser visible en dark y light theme."""

    def test_splitter_handle_not_too_dark(self):
        """rgba(0,0,0,0.08) es invisible en dark mode — debe usar rgba con mayor contraste."""
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "rgba(0,0,0,0.08)" not in src, (
            "rgba(0,0,0,0.08) es invisible en dark theme. "
            "Usar rgba(148,163,184,0.25) o similar."
        )

    def test_splitter_handle_uses_neutral_rgba(self):
        """El handle debe usar un rgba neutral visible en ambos temas."""
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        # Should use a visible rgba — check common neutral patterns
        has_visible = (
            "rgba(148,163,184" in src or
            "rgba(100,116,139" in src or
            "rgba(203,213,225" in src
        )
        assert has_visible, (
            "QSplitter handle debe usar un rgba neutral visible en ambos temas, "
            "como rgba(148,163,184,0.25)"
        )


# ── Print HTML exemption ─────────────────────────────────────────────────────

class TestPrintHTMLExemption:
    """HTML generado para impresión usa literales — exempto de tokens de tema."""

    def test_generar_html_compra_no_slate50_token(self):
        """_generar_html_compra no debe usar Colors.NEUTRAL.SLATE_50 (usar literal)."""
        src = _method_src("_generar_html_compra")
        assert src is not None
        assert "NEUTRAL.SLATE_50" not in src, (
            "_generar_html_compra no debe usar Colors.NEUTRAL.SLATE_50. "
            "Usar literal '#f8fafc' ya que es HTML de impresión — "
            "el CSS de tema de la app no se aplica a QPrinter."
        )

    def test_generar_html_compra_no_neutral_white_token(self):
        """_generar_html_compra no debe usar Colors.NEUTRAL.WHITE (usar literal)."""
        src = _method_src("_generar_html_compra")
        assert src is not None
        assert "NEUTRAL.WHITE" not in src, (
            "_generar_html_compra no debe usar Colors.NEUTRAL.WHITE. "
            "Usar literal '#ffffff' para HTML de impresión."
        )

    def test_generar_html_compra_has_print_exempt_comment(self):
        """Debe haber un comentario explicando la excepción de print HTML."""
        src = _method_src("_generar_html_compra")
        assert src is not None
        assert "print" in src.lower() or "impresión" in src.lower() or "impresion" in src.lower(), (
            "_generar_html_compra debe tener comentario explicando que usa colores "
            "fijos porque es HTML de impresión (no widget de tema)"
        )


# ── Global scan — no banned backgrounds in active rendering methods ──────────

# All methods that render visible widgets (excludes print HTML)
_ACTIVE_RENDERING_METHODS = [
    "_build_ui",
    "_build_tab_tradicional",
    "_build_purchase_kpi_bar",
    "_build_provider_card",
    "_build_document_card",
    "_build_product_search_card",
    "_build_purchase_items_panel",
    "_build_purchase_totals_footer",
    "_build_dynamic_action_button",
    "_build_quick_products_card",
    "_build_center_column",
    "_build_tab_qr",
    "_build_documental_toolbar",
    "_build_summary_panel",
    "_build_stepper_bar",
    "_build_tab_historial",
    "_build_hist_kpi_sidebar",
]


class TestNoSLATE50InActiveWidgets:
    """SLATE_50 no debe aparecer como background en ningún método de renderizado activo."""

    @pytest.mark.parametrize("method_name", _ACTIVE_RENDERING_METHODS)
    def test_no_slate50_background_in_active_method(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"Method {method_name} not found")
        offenses = _has_slate50_as_background(src)
        assert not offenses, (
            f"SLATE_50 como background en {method_name}: {offenses}. "
            f"Usar background:transparent para compatibilidad con dark theme."
        )


class TestNoBackgroundWhiteInActiveWidgets:
    """background:white no debe aparecer en ningún método de renderizado activo."""

    @pytest.mark.parametrize("method_name", _ACTIVE_RENDERING_METHODS)
    def test_no_background_white_in_active_method(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"Method {method_name} not found")
        offenses = _has_background_white(src)
        assert not offenses, (
            f"background:white en {method_name}: {offenses}. "
            f"No compatible con dark theme."
        )


class TestNoNeutralWhiteBackgroundInWidgets:
    """Colors.NEUTRAL.WHITE no debe usarse como background de widget en métodos activos."""

    @pytest.mark.parametrize("method_name", _ACTIVE_RENDERING_METHODS)
    def test_no_neutral_white_background_in_active_method(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"Method {method_name} not found")
        offenses = _has_neutral_white_background(src)
        assert not offenses, (
            f"Colors.NEUTRAL.WHITE como background en {method_name}: {offenses}"
        )


# ── FASE 10 dead code cleanup ────────────────────────────────────────────────

class TestDeadCodeColorStatus:
    """FASE 10 elimina _build_provider_sidebar y sus estilos obsoletos."""

    def test_provider_sidebar_removed(self):
        assert _method_src("_build_provider_sidebar") is None

    def test_provider_sidebar_not_called(self):
        assert "_build_provider_sidebar()" not in _source()

    def test_removed_dead_code_hex_not_present(self):
        assert "QListWidget::item:hover{background:#F8FAFC;}" not in _source()
