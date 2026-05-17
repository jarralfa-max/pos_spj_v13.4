"""
Phase 9 characterization tests — QR/PO reception UI/UX improvements.
Verify structural changes, new widgets, helpers, and QR NO-TOUCH invariants.
"""
import ast
import re
import os
import pytest

QR_SRC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "modulos", "recepcion_qr_widget.py"
)
COMPRAS_SRC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "modulos", "compras_pro.py"
)


def _qr() -> str:
    return open(QR_SRC_PATH).read()


def _compras() -> str:
    return open(COMPRAS_SRC_PATH).read()


# ---------------------------------------------------------------------------
# Sintaxis
# ---------------------------------------------------------------------------
class TestSyntax:
    def test_qr_widget_no_syntax_error(self):
        ast.parse(_qr())

    def test_compras_pro_no_syntax_error(self):
        ast.parse(_compras())


# ---------------------------------------------------------------------------
# QR NO-TOUCH: pestañas 1-4 intactas
# ---------------------------------------------------------------------------
QR_PROTECTED_METHODS = [
    "_build_tab_generar",
    "_build_tab_asignar",
    "_build_tab_recepcionar",
    "_build_tab_historial",
    "_activar_lector_qr",
]


@pytest.mark.parametrize("method", QR_PROTECTED_METHODS)
def test_qr_protected_methods_present(method):
    assert f"def {method}" in _qr(), f"Protected QR method removed: {method}"


def test_qr_tabs_count_unchanged():
    src = _qr()
    tabs = re.findall(r"addTab\(", src)
    assert len(tabs) >= 5, "Expected 5 tabs (4 QR + 1 PO)"


def test_qr_engine_not_duplicated_in_compras():
    compras = _compras()
    assert "_activar_lector_qr" not in compras
    assert "trazabilidad_qr" not in compras


# ---------------------------------------------------------------------------
# Phase 9: nuevos widgets en _build_tab_po_recepcion
# ---------------------------------------------------------------------------
PHASE9_ATTRS = [
    "self._lbl_po_estado_badge",
    "self._po_summary_frame",
    "self._sum_esperado",
    "self._sum_recibido",
    "self._sum_a_recibir",
    "self._sum_diferencia",
    "self._sum_pct",
]


@pytest.mark.parametrize("attr", PHASE9_ATTRS)
def test_phase9_widget_attr_exists(attr):
    assert attr in _qr(), f"Phase 9 attribute missing: {attr}"


def test_phase9_delta_column_8_columns():
    """Tabla debe tener 8 columnas (era 7 en Phase 6)."""
    src = _qr()
    assert "setColumnCount(8)" in src


def test_phase9_delta_column_header():
    src = _qr()
    assert "Δ Diferencia" in src or "Delta" in src or "diferencia" in src.lower()


# ---------------------------------------------------------------------------
# Phase 9: métodos helper
# ---------------------------------------------------------------------------
PHASE9_METHODS = [
    "_set_po_estado_badge",
    "_on_spin_qty_changed",
    "_update_po_summary",
]


@pytest.mark.parametrize("method", PHASE9_METHODS)
def test_phase9_helper_method_exists(method):
    assert f"def {method}" in _qr(), f"Phase 9 method missing: {method}"


# ---------------------------------------------------------------------------
# _set_po_estado_badge: usa Colors.* para todos los estados
# ---------------------------------------------------------------------------
def test_badge_uses_colors_tokens():
    src = _qr()
    m = re.search(r"def _set_po_estado_badge.*?(?=\n    def )", src, re.DOTALL)
    assert m, "_set_po_estado_badge not found"
    body = m.group(0)
    # Must reference Colors tokens, not bare hex strings
    bare_hex = re.findall(r'"#[0-9a-fA-F]{6,8}"', body)
    assert len(bare_hex) == 0, f"Bare hex in badge method: {bare_hex}"
    assert "Colors." in body


BADGE_ESTADOS = ["ABIERTA", "PARCIAL", "RECIBIDA", "CERRADA", "CANCELADA"]


@pytest.mark.parametrize("estado", BADGE_ESTADOS)
def test_badge_handles_estado(estado):
    src = _qr()
    m = re.search(r"def _set_po_estado_badge.*?(?=\n    def )", src, re.DOTALL)
    assert m
    assert estado in m.group(0)


# ---------------------------------------------------------------------------
# _update_po_summary: calcula Δ y % completitud
# ---------------------------------------------------------------------------
def test_update_po_summary_calculates_delta():
    src = _qr()
    m = re.search(r"def _update_po_summary.*?(?=\n    def )", src, re.DOTALL)
    assert m, "_update_po_summary not found"
    body = m.group(0)
    assert "delta" in body.lower() or "diferencia" in body.lower()
    assert "pct" in body.lower() or "completitud" in body.lower() or "%" in body


def test_update_po_summary_uses_colors_tokens():
    src = _qr()
    m = re.search(r"def _update_po_summary.*?(?=\n    def )", src, re.DOTALL)
    assert m
    body = m.group(0)
    bare_hex = re.findall(r'"#[0-9a-fA-F]{6,8}"', body)
    assert len(bare_hex) == 0, f"Bare hex in summary: {bare_hex}"


# ---------------------------------------------------------------------------
# _on_spin_qty_changed: actualiza Δ en fila y refresca summary
# ---------------------------------------------------------------------------
def test_spin_changed_updates_summary():
    src = _qr()
    m = re.search(r"def _on_spin_qty_changed.*?(?=\n    def )", src, re.DOTALL)
    assert m, "_on_spin_qty_changed not found"
    body = m.group(0)
    assert "_update_po_summary" in body


def test_spin_connected_to_on_spin_changed():
    """El spinner de cantidad debe conectarse al slot en tiempo real."""
    src = _qr()
    assert "_on_spin_qty_changed" in src
    assert "valueChanged" in src


# ---------------------------------------------------------------------------
# _aceptar_todo_po: también refresca summary (Phase 9)
# ---------------------------------------------------------------------------
def test_aceptar_todo_refreshes_summary():
    src = _qr()
    m = re.search(r"def _aceptar_todo_po.*?(?=\n    def )", src, re.DOTALL)
    assert m, "_aceptar_todo_po not found"
    assert "_update_po_summary" in m.group(0)


# ---------------------------------------------------------------------------
# _confirmar_recepcion_po: actualiza badge con nuevo estado tras éxito
# ---------------------------------------------------------------------------
def test_confirmar_po_updates_badge():
    src = _qr()
    m = re.search(r"def _confirmar_recepcion_po.*?(?=\n    def |\Z)", src, re.DOTALL)
    assert m
    body = m.group(0)
    assert "_set_po_estado_badge" in body


# ---------------------------------------------------------------------------
# No duplicación de inventario: ReceivePOAdapter es el único camino
# ---------------------------------------------------------------------------
def test_no_direct_inventory_in_phase9_helpers():
    """Los nuevos helpers Phase 9 no tocan inventario directamente."""
    src = _qr()
    phase9_helpers = re.findall(
        r"def (_set_po_estado_badge|_on_spin_qty_changed|_update_po_summary).*?(?=\n    def |\Z)",
        src, re.DOTALL
    )
    for body in phase9_helpers:
        # No UPDATE inventario_actual ni INSERT kardex en helpers UI
        assert "inventario_actual" not in body
        assert "kardex" not in body
        assert "add_stock" not in body


# ---------------------------------------------------------------------------
# Summary frame usa Colors.* (no hex hardcodeado)
# ---------------------------------------------------------------------------
def test_summary_frame_no_bare_hex():
    src = _qr()
    m = re.search(r"self\._po_summary_frame.*?lay\.addWidget\(self\._po_summary_frame\)", src, re.DOTALL)
    if not m:
        # Busca el bloque de creación del frame más amplio
        m = re.search(r"poSummaryFrame.*?self\._po_summary_frame\.hide\(\)", src, re.DOTALL)
    if m:
        section = m.group(0)
        bare_hex = re.findall(r'"#[0-9a-fA-F]{6,8}"', section)
        assert len(bare_hex) == 0, f"Bare hex in summary frame: {bare_hex}"


# ---------------------------------------------------------------------------
# objectName para badge (para CSS theming)
# ---------------------------------------------------------------------------
def test_badge_has_object_name():
    src = _qr()
    assert '"poEstadoBadge"' in src or "'poEstadoBadge'" in src


def test_summary_frame_has_object_name():
    src = _qr()
    assert '"poSummaryFrame"' in src or "'poSummaryFrame'" in src
