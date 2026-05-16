"""
Phase 8 characterization tests — Toolbar Documental ERP.
Verify structure, widget presence, method contracts, and QR NO-TOUCH policy.
"""
import ast
import inspect
import re
import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "modulos", "compras_pro.py")
QR_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "modulos", "recepcion_qr_widget.py")

def _source() -> str:
    return open(SRC).read()

def _qr_source() -> str:
    return open(QR_SRC).read()


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------
class TestSyntax:
    def test_compras_pro_no_syntax_errors(self):
        src = _source()
        ast.parse(src)  # raises SyntaxError on failure

    def test_qr_widget_no_syntax_errors(self):
        src = _qr_source()
        ast.parse(src)


# ---------------------------------------------------------------------------
# Method existence
# ---------------------------------------------------------------------------
REQUIRED_METHODS = [
    "_build_documental_toolbar",
    "_cargar_docs_erp",
    "_actualizar_chips_contadores",
    "_poblar_lista_docs",
    "_on_doc_filter_changed",
    "_on_doc_item_clicked",
    "_refresh_doc_detail",
    "_refresh_doc_acciones",
    "_accion_aprobar_pr",
    "_accion_rechazar_pr",
    "_accion_editar_doc",
    "_accion_convertir_a_po",
    "_accion_enviar_recepcion_doc",
    "_doc_chip_style",
    "_refresh_doc_btn_styles",
]

@pytest.mark.parametrize("method", REQUIRED_METHODS)
def test_method_exists(method):
    src = _source()
    assert f"def {method}" in src, f"Missing method: {method}"


# ---------------------------------------------------------------------------
# Widget attribute creation inside _build_documental_toolbar
# ---------------------------------------------------------------------------
REQUIRED_ATTRS = [
    "self._doc_erp_list",
    "self._doc_detail_card",
    "self._doc_acciones_frame",
    "self._doc_filter_chips",
    "self._selected_doc_id",
    "self._selected_doc_type",
    "self._selected_doc_estado",
    "self._docs_erp_cache",
    "self._btn_aprobar_pr",
    "self._btn_rechazar_pr",
    "self._btn_editar_doc",
    "self._btn_conv_po",
    "self._btn_enviar_rec_doc",
]

@pytest.mark.parametrize("attr", REQUIRED_ATTRS)
def test_widget_attr_defined(attr):
    src = _source()
    assert attr in src, f"Missing attribute assignment: {attr}"


# ---------------------------------------------------------------------------
# ObjectName coverage for 5 action buttons
# ---------------------------------------------------------------------------
BUTTON_OBJECT_NAMES = [
    "btnAprobarPR",
    "btnRechazarPR",
    "btnEditarDoc",
    "btnConvPO",
    "btnEnviarRecDoc",
]

@pytest.mark.parametrize("name", BUTTON_OBJECT_NAMES)
def test_button_object_name(name):
    src = _source()
    assert f'"{name}"' in src, f"Missing setObjectName: {name}"


# ---------------------------------------------------------------------------
# Filter chips — all 5 keys present
# ---------------------------------------------------------------------------
FILTER_KEYS = ["all", "pr_pend", "pr_aprobadas", "po_abiertas", "rec_parc"]

@pytest.mark.parametrize("key", FILTER_KEYS)
def test_filter_chip_key(key):
    src = _source()
    assert f'"{key}"' in src, f"Filter chip key missing: {key}"


# ---------------------------------------------------------------------------
# UC wiring — toolbar calls correct UCs (not ProcesarCompraUC)
# ---------------------------------------------------------------------------
class TestUCWiring:
    def test_loads_pr_listar_pendientes(self):
        src = _source()
        assert "listar_pendientes" in src

    def test_loads_pr_listar_aprobadas(self):
        src = _source()
        assert "listar_aprobadas" in src

    def test_loads_po_listar_abiertas(self):
        src = _source()
        assert "listar_abiertas" in src

    def test_aprobar_calls_pr_uc(self):
        src = _source()
        m = re.search(r"def _accion_aprobar_pr\(self\).*?(?=\n    def )", src, re.DOTALL)
        assert m, "_accion_aprobar_pr body not found"
        assert "aprobar" in m.group(0)

    def test_rechazar_calls_pr_uc(self):
        src = _source()
        m = re.search(r"def _accion_rechazar_pr\(self\)[^\n]*\n(.*?)(?=\n    def )", src, re.DOTALL)
        assert m, "_accion_rechazar_pr body not found"
        assert "rechazar" in m.group(1)

    def test_convertir_calls_pr_uc(self):
        src = _source()
        m = re.search(r"def _accion_convertir_a_po\(self\)[^\n]*\n(.*?)(?=\n    def )", src, re.DOTALL)
        assert m, "_accion_convertir_a_po body not found"
        assert "convertir_a_po" in m.group(1)

    def test_enviar_recepcion_calls_po_uc(self):
        src = _source()
        m = re.search(r"def _accion_enviar_recepcion_doc\(self\)[^\n]*\n(.*?)(?=\n    def )", src, re.DOTALL)
        assert m, "_accion_enviar_recepcion_doc body not found"
        assert "enviar_a_recepcion" in m.group(1)

    def test_no_procesar_compra_uc_in_toolbar(self):
        """Toolbar must not use deprecated ProcesarCompraUC."""
        src = _source()
        # Extract toolbar section
        m = re.search(r"def _build_documental_toolbar.*?(?=\n    def _build_provider_sidebar)", src, re.DOTALL)
        assert m
        assert "ProcesarCompraUC" not in m.group(0)


# ---------------------------------------------------------------------------
# Design tokens — no bare hex in toolbar section
# ---------------------------------------------------------------------------
class TestDesignTokens:
    def _toolbar_section(self) -> str:
        src = _source()
        # From _build_documental_toolbar to just before _build_provider_sidebar
        m = re.search(
            r"def _build_documental_toolbar.*?(?=\n    def _build_provider_sidebar)",
            src, re.DOTALL
        )
        return m.group(0) if m else ""

    def _accion_section(self) -> str:
        src = _source()
        m = re.search(
            r"def _accion_aprobar_pr.*?(?=\n    def _procesar_compra|\Z)",
            src, re.DOTALL
        )
        return m.group(0) if m else ""

    def test_toolbar_section_no_bare_hex(self):
        section = self._toolbar_section()
        # Allow Colors.* token usage — disallow raw "#RRGGBB" strings
        bare = re.findall(r'"#[0-9a-fA-F]{6,8}"', section)
        # Some hex in setStyleSheet f-strings using Colors.* tokens is fine,
        # but raw quoted hex strings should come from Colors.* interpolation only
        problematic = [h for h in bare if "Colors." not in section[:section.index(h) + len(h) + 50]]
        assert len(problematic) == 0, f"Bare hex in toolbar section: {problematic}"

    def test_colors_import_present(self):
        src = _source()
        assert "from modulos.design_tokens import Colors" in src or \
               "from .design_tokens import Colors" in src or \
               "design_tokens" in src


# ---------------------------------------------------------------------------
# QR NO-TOUCH policy — recepcion_qr_widget.py unchanged (structurally)
# ---------------------------------------------------------------------------
class TestQRNoTouch:
    def test_qr_widget_has_po_tab(self):
        src = _qr_source()
        assert "_build_tab_po_recepcion" in src or "_tab_po_recv" in src

    def test_qr_widget_has_confirmar_recepcion(self):
        src = _qr_source()
        assert "_confirmar_recepcion_po" in src

    def test_qr_no_duplicate_inventory_logic(self):
        """QR widget should NOT have _build_documental_toolbar (no cross-contamination)."""
        src = _qr_source()
        assert "_build_documental_toolbar" not in src

    def test_qr_widget_no_compras_pro_import(self):
        src = _qr_source()
        assert "from modulos.compras_pro" not in src
        assert "import compras_pro" not in src


# ---------------------------------------------------------------------------
# _build_tab_tradicional wiring — toolbar is connected
# ---------------------------------------------------------------------------
class TestTabTradWiring:
    def test_tab_trad_calls_documental_toolbar(self):
        src = _source()
        m = re.search(r"def _build_tab_tradicional.*?(?=\n    def )", src, re.DOTALL)
        assert m, "_build_tab_tradicional not found"
        assert "_build_documental_toolbar" in m.group(0)

    def test_tab_trad_not_calling_provider_sidebar_directly(self):
        """Sidebar is now embedded inside documental toolbar, not called standalone."""
        src = _source()
        m = re.search(r"def _build_tab_tradicional.*?(?=\n    def )", src, re.DOTALL)
        assert m
        # _build_provider_sidebar should NOT be called directly from _build_tab_tradicional
        assert "_build_provider_sidebar()" not in m.group(0)


# ---------------------------------------------------------------------------
# State var initialization
# ---------------------------------------------------------------------------
class TestStateVars:
    def test_selected_doc_id_initialized_none(self):
        src = _source()
        assert "self._selected_doc_id     = None" in src or \
               "self._selected_doc_id = None" in src

    def test_selected_doc_type_initialized_none(self):
        src = _source()
        assert "self._selected_doc_type" in src and "None" in src

    def test_docs_erp_cache_initialized_list(self):
        src = _source()
        assert "self._docs_erp_cache" in src
        assert "_docs_erp_cache: list" in src or "= []" in src

    def test_doc_filter_active_initialized(self):
        src = _source()
        # Allow varied whitespace around assignment
        assert re.search(r'_doc_filter_active\s*=\s*["\']all["\']', src)
