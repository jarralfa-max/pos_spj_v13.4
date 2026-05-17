"""
tests/purchases/test_fase3_layout_contract.py
──────────────────────────────────────────────
FASE 3 — Contrato del layout de 3 columnas de Compra Tradicional.

Verifica mediante AST (sin instanciar PyQt5) que:
- El layout es QSplitter de 3 columnas
- Las proporciones siguen col-span 3|4|5: setSizes([280, 360, 450])
  con setStretchFactor(1, 4) para centro y setStretchFactor(2, 5) para derecha
- Columna izquierda = documental toolbar (ERP PR/PO)
- Columna central = center column (proveedor → documento → búsqueda → partidas)
- Columna derecha = summary panel (totales + acción)
- KPI bar FUERA de las tabs (en _build_ui, no dentro de _build_tab_tradicional)
- Sin PROVEEDOR RÁPIDO visible en columna izquierda
- _build_provider_sidebar fue eliminado en FASE 10
- Widgets backward-compat están ocultos (no visibles al usuario)
- No hay SLATE_50 como background en los métodos del área Compra Tradicional
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import re
import pytest


def _source() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, "modulos", "compras_pro.py"), encoding="utf-8").read()


def _method_src(method_name: str, class_name: str = "ModuloComprasPro") -> str | None:
    src = _source()
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


# ── Componentes Fase 3 ───────────────────────────────────────────────────────

class TestPhase3ComponentClasses:
    """Los componentes semánticos de Compra Tradicional deben existir y usarse."""

    REQUIRED = [
        "PurchaseKpiBar",
        "PurchaseDocumentToolbar",
        "PurchaseCapturePanel",
        "PurchaseProviderCard",
        "PurchaseDocumentCard",
        "PurchaseProductSearchCard",
        "PurchaseQuickProductsCard",
        "PurchaseItemsAndTotalsPanel",
        "PurchaseTotalsFooter",
        "PurchaseDynamicActionBar",
    ]

    def test_component_classes_defined(self):
        src = _source()
        tree = ast.parse(src)
        classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        missing = [name for name in self.REQUIRED if name not in classes]
        assert not missing, f"Componentes Fase 3 faltantes: {missing}"

    def test_component_classes_used_by_builders(self):
        src = _source()
        for name in self.REQUIRED:
            assert src.count(name) >= 2, f"{name} debe definirse y usarse en builders"


# ── Splitter layout ──────────────────────────────────────────────────────────

class TestSplitterLayout:
    """_build_tab_tradicional debe usar QSplitter de 3 columnas."""

    def test_build_tab_tradicional_imports_or_uses_splitter(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "QSplitter" in src, "_build_tab_tradicional debe usar QSplitter"

    def test_splitter_sizes_col_span_3_4_5(self):
        """Sizes must follow exact col-span 3|4|5: [285, 380, 475]."""
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "285" in src, "setSizes debe incluir 285 para columna izquierda (col-span-3)"
        assert "setSizes" in src, "setSizes debe llamarse en _build_tab_tradicional"

    def test_splitter_set_sizes_list_correct(self):
        """setSizes must be [285, 380, 475] — exact 3:4:5 at 1140px reference."""
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        match = re.search(r'setSizes\(\[(\d+),\s*(\d+),\s*(\d+)\]\)', src)
        assert match is not None, "setSizes([...]) debe estar en _build_tab_tradicional"
        sizes = [int(match.group(i)) for i in (1, 2, 3)]
        left, center, right = sizes
        assert sizes == [285, 380, 475], (
            f"Sizes incorrectos: {sizes}. Esperado: [285, 380, 475] (col-span 3:4:5)"
        )

    def test_stretch_factor_center_column_is_4(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "setStretchFactor(1, 4)" in src, (
            "setStretchFactor(1, 4) debe estar en _build_tab_tradicional "
            "(columna central = índice 1, factor = 4 para col-span-4)"
        )

    def test_stretch_factor_left_col_is_0(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "setStretchFactor(0, 0)" in src, (
            "setStretchFactor(0, 0) debe estar — columna izquierda no crece"
        )

    def test_stretch_factor_right_col_is_5(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "setStretchFactor(2, 5)" in src, (
            "setStretchFactor(2, 5) debe estar — columna derecha crece como col-span-5"
        )

    def test_exactly_3_columns_added_to_splitter(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        count = src.count("splitter.addWidget(")
        assert count == 3, (
            f"QSplitter debe tener exactamente 3 columnas, encontradas: {count}"
        )


# ── Column assignment ────────────────────────────────────────────────────────

class TestColumnAssignment:
    """Cada columna debe ser construida por el método correcto."""

    def test_left_col_is_documental_toolbar(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_build_documental_toolbar" in src, (
            "La columna izquierda debe construirse con _build_documental_toolbar()"
        )

    def test_center_col_is_center_column(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_build_center_column" in src, (
            "La columna central debe construirse con _build_center_column()"
        )

    def test_right_col_is_summary_panel(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_build_summary_panel" in src, (
            "La columna derecha debe construirse con _build_summary_panel()"
        )

    def test_center_column_contains_provider_card(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_build_provider_card" in src, (
            "_build_center_column debe incluir _build_provider_card() como primera sección"
        )

    def test_center_column_contains_document_card(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_build_document_card" in src

    def test_center_column_contains_product_search(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_build_product_search_card" in src

    def test_center_column_provider_before_document(self):
        """El proveedor debe aparecer antes del documento en la columna central."""
        src = _method_src("_build_center_column")
        assert src is not None
        pos_prov = src.find("_build_provider_card")
        pos_doc = src.find("_build_document_card")
        assert pos_prov < pos_doc, (
            "_build_provider_card debe aparecer antes que _build_document_card en _build_center_column"
        )

    def test_summary_panel_contains_items_panel(self):
        src = _method_src("_build_summary_panel")
        assert src is not None
        assert "_build_purchase_items_panel" in src

    def test_summary_panel_contains_action_button(self):
        src = _method_src("_build_summary_panel")
        assert src is not None
        assert "_build_dynamic_action_button" in src


# ── KPI bar placement ────────────────────────────────────────────────────────

class TestKPIBarPlacement:
    """El KPI bar debe estar FUERA de las tabs (en _build_ui), no dentro de un tab."""

    def test_kpi_bar_called_in_build_ui(self):
        src = _method_src("_build_ui")
        assert src is not None
        assert "_build_purchase_kpi_bar" in src, (
            "_build_purchase_kpi_bar() debe llamarse en _build_ui, "
            "FUERA de los tabs — se muestra en todas las pestañas"
        )

    def test_kpi_bar_not_called_inside_build_tab_tradicional(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_build_purchase_kpi_bar" not in src, (
            "_build_purchase_kpi_bar NO debe llamarse dentro de _build_tab_tradicional. "
            "El KPI bar está fuera de los tabs, no se duplica dentro del tab."
        )

    def test_kpi_bar_not_called_inside_build_center_column(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_build_purchase_kpi_bar" not in src

    def test_kpi_bar_method_exists(self):
        src = _source()
        assert "_build_purchase_kpi_bar" in src

    def test_kpi_strip_cards_stored_as_list(self):
        src = _method_src("_build_purchase_kpi_bar")
        assert src is not None
        assert "_kpi_strip_cards" in src, (
            "_kpi_strip_cards debe existir para permitir el refresco de KPIs"
        )


# ── Left column content ──────────────────────────────────────────────────────

class TestLeftColumnContent:
    """La columna izquierda contiene solo documentos ERP, sin PROVEEDOR RÁPIDO visible."""

    def test_documental_toolbar_uses_erp_width_bounds(self):
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "setMinimumWidth(260)" in src
        assert "setMaximumWidth(320)" in src
        assert "setFixedWidth(260)" not in src

    def test_no_proveedor_rapido_visible_in_documental_toolbar(self):
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "PROVEEDOR RÁPIDO" not in src and "RÁPIDO" not in src, (
            "PROVEEDOR RÁPIDO no debe aparecer en la columna izquierda. "
            "El selector de proveedor está en la columna central."
        )

    def test_sidebar_prov_search_is_hidden_in_toolbar(self):
        """_sidebar_prov_search debe crearse oculto (backward-compat, no visible)."""
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "_sidebar_prov_search" in src, (
            "_sidebar_prov_search debe existir en _build_documental_toolbar para backward-compat"
        )
        # Find creation and check that .hide() follows
        pos = src.find("_sidebar_prov_search")
        block = src[pos:pos + 200]
        assert ".hide()" in block, (
            "_sidebar_prov_search debe ocultarse en _build_documental_toolbar"
        )

    def test_sidebar_prov_list_is_hidden_in_toolbar(self):
        """_sidebar_prov_list debe crearse oculto (backward-compat, no visible)."""
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "_sidebar_prov_list" in src
        pos = src.find("_sidebar_prov_list")
        block = src[pos:pos + 200]
        assert ".hide()" in block

    def test_documentos_erp_label_in_toolbar(self):
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "DOCUMENTOS ERP" in src or "documentos erp" in src.lower()

    def test_filter_chips_in_toolbar(self):
        """La toolbar debe tener filtros de documentos (all, pr_pend, pr_aprobadas, po_abiertas)."""
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "_doc_filter_chips" in src


# ── FASE 10 dead code cleanup ────────────────────────────────────────────────

class TestDeadCodeGuard:
    """_build_provider_sidebar fue eliminado; no debe volver al layout."""

    def test_provider_sidebar_method_removed(self):
        assert _method_src("_build_provider_sidebar") is None

    def test_provider_sidebar_not_called_from_build_tab_tradicional(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_build_provider_sidebar" not in src

    def test_provider_sidebar_not_called_from_build_center_column(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_build_provider_sidebar" not in src

    def test_provider_sidebar_not_called_from_build_documental_toolbar(self):
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "_build_provider_sidebar" not in src

    def test_provider_sidebar_not_called_from_build_ui(self):
        src = _method_src("_build_ui")
        assert src is not None
        assert "_build_provider_sidebar" not in src


# ── Theme safety (Compra Tradicional scope) ──────────────────────────────────

class TestThemeSafetyInTradicionalScope:
    """Los métodos del área Compra Tradicional no deben usar SLATE_50 como fondo."""

    TRADICIONAL_METHODS = [
        "_build_tab_tradicional",
        "_build_documental_toolbar",
        "_build_center_column",
        "_build_provider_card",
        "_build_document_card",
        "_build_product_search_card",
        "_build_summary_panel",
        "_build_purchase_items_panel",
        "_build_dynamic_action_button",
    ]

    def _check_no_slate50_background(self, method_name: str) -> None:
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"Method {method_name} not found")
        # Look for SLATE_50 used as background (not as color for text)
        matches = re.findall(r'background[^;]*SLATE_50', src)
        for m in matches:
            # Color tokens for text are OK: "color:...SLATE_50"
            if "color:" not in m.split("background")[0][-20:]:
                pytest.fail(
                    f"SLATE_50 usado como background en {method_name}: '{m}'. "
                    f"Usar background:transparent para compatibilidad con dark theme."
                )

    def test_no_slate50_background_in_build_tab_tradicional(self):
        self._check_no_slate50_background("_build_tab_tradicional")

    def test_no_slate50_background_in_build_documental_toolbar(self):
        self._check_no_slate50_background("_build_documental_toolbar")

    def test_no_slate50_background_in_build_center_column(self):
        self._check_no_slate50_background("_build_center_column")

    def test_no_slate50_background_in_build_provider_card(self):
        self._check_no_slate50_background("_build_provider_card")

    def test_no_slate50_background_in_build_document_card(self):
        self._check_no_slate50_background("_build_document_card")

    def test_no_slate50_background_in_build_summary_panel(self):
        self._check_no_slate50_background("_build_summary_panel")

    def test_no_slate50_background_in_build_items_panel(self):
        self._check_no_slate50_background("_build_purchase_items_panel")

    def test_no_background_white_in_documental_toolbar(self):
        src = _method_src("_build_documental_toolbar")
        assert src is not None
        assert "background:white" not in src and "background: white" not in src, (
            "background:white no permitido en _build_documental_toolbar — no funciona en dark theme"
        )

    def test_no_background_white_in_center_column(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "background:white" not in src and "background: white" not in src

    def test_no_background_white_in_summary_panel(self):
        src = _method_src("_build_summary_panel")
        assert src is not None
        assert "background:white" not in src and "background: white" not in src


# ── Hidden backward-compat widgets ──────────────────────────────────────────

class TestHiddenBackwardCompatWidgets:
    """Los widgets backward-compat deben estar almacenados como attrs para evitar GC."""

    def test_hidden_doctype_toolbar_stored(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_hidden_doctype_toolbar" in src, (
            "_hidden_doctype_toolbar debe guardarse en _build_center_column "
            "para evitar que Python GC destruya el objeto C++."
        )

    def test_hidden_stepper_stored(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_hidden_stepper" in src

    def test_doctype_toolbar_added_to_layout(self):
        """FASE 6: doctype toolbar is now visible in center column layout (no unconditional hide)."""
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_hidden_doctype_toolbar = self._build_doctype_toolbar()" in src, (
            "_hidden_doctype_toolbar debe construirse en _build_center_column"
        )
        assert "lay.addWidget(self._hidden_doctype_toolbar)" in src, (
            "FASE 6: doctype toolbar debe añadirse al layout (visible). "
            "No debe eliminarse con .hide() incondicional."
        )

    def test_hidden_stepper_is_hidden(self):
        src = _method_src("_build_center_column")
        assert src is not None
        idx = src.find("_hidden_stepper")
        block = src[idx:idx + 100]
        assert ".hide()" in block
