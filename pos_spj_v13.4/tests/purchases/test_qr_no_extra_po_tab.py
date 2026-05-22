"""
FASE 2 — No regresión de pestañas PO separadas.

Fase 2 impide una pestaña principal o interna separada para PO.
La recepción contra orden vive como submodo/panel dentro de “Recepción con QR”.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FORBIDDEN_PO_TAB_LABELS = (
    "Recepción de PO",
    "Recepcion de PO",
    "Recepción PO",
    "Recepcion PO",
    "Recepción OC",
    "Recepcion OC",
    "PO Reception",
    "Recibir Orden",
)


def _source(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _method_source(rel_path: str, method_name: str) -> str:
    src = _source(rel_path)
    tree = ast.parse(src, filename=rel_path)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Método {method_name} no encontrado en {rel_path}")


def test_no_hay_cuarta_tab_principal_para_po():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    assert build_ui.count(".addTab(") == 3
    for label in FORBIDDEN_PO_TAB_LABELS:
        assert label not in build_ui


def test_no_hay_widget_po_reception_en_modulo_principal():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    assert "_tab_po_recv" not in build_ui
    assert "_build_tab_po_recepcion" not in build_ui


def test_accion_enviar_recepcion_usa_tab_qr_no_tab_po_externa():
    method = _method_source("modulos/compras_pro.py", "_accion_enviar_recepcion_doc")
    assert "setCurrentIndex(1)" in method, "Debe cambiar a la tab principal Recepción con QR"
    assert "setCurrentIndex(3)" not in method
    assert "setCurrentIndex(4)" not in method


def test_fase2_no_existe_tab_interna_llamada_recepcion_po():
    qr_build_ui = _method_source("modulos/recepcion_qr_widget.py", "_build_ui")
    assert qr_build_ui.count(".addTab(") == 4
    assert "_tab_po_recv" not in qr_build_ui
    for label in FORBIDDEN_PO_TAB_LABELS:
        assert label not in qr_build_ui


def test_fase2_po_vive_como_submodo_de_recepcionar():
    qr_src = _source("modulos/recepcion_qr_widget.py")
    recepcionar = _method_source("modulos/recepcion_qr_widget.py", "_build_tab_recepcionar")
    assert "_cmb_recepcion_origen" in recepcionar
    assert "_recv_origin_stack" in recepcionar
    assert "_po_receipt_panel" in recepcionar
    assert "def _build_po_reception_panel" in qr_src


def test_qr_widget_sigue_importable_para_no_tocar_motor_qr():
    try:
        import modulos.recepcion_qr_widget as qr
    except ImportError as exc:
        msg = str(exc)
        if "libGL.so.1" in msg or "PyQt5" in msg or "No module named" in msg:
            pytest.skip(f"PyQt5 runtime dependency unavailable in this environment: {exc}")
        raise

    assert hasattr(qr, "RecepcionQRWidget")


def test_guard_elimina_tabs_po_accidentales_en_qr_widget():
    method = _method_source("modulos/recepcion_qr_widget.py", "_remove_accidental_po_tabs")
    assert "removeTab" in method
    assert "recepcion po" in method
    assert "po reception" in method
    build_ui = _method_source("modulos/recepcion_qr_widget.py", "_build_ui")
    assert "_remove_accidental_po_tabs()" in build_ui


def test_guard_elimina_tabs_po_accidentales_en_modulo_compras():
    method = _method_source("modulos/compras_pro.py", "_remove_accidental_po_tabs")
    assert "removeTab" in method
    assert "recepcion po" in method
    assert "po reception" in method
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    assert "_remove_accidental_po_tabs()" in build_ui


def test_phase8_selector_incluye_qr_po_transferencia_sin_tabs_nuevas():
    recepcionar = _method_source("modulos/recepcion_qr_widget.py", "_build_tab_recepcionar")
    qr_build_ui = _method_source("modulos/recepcion_qr_widget.py", "_build_ui")
    assert qr_build_ui.count(".addTab(") == 4
    assert 'addItem("QR / Contenedor", "QR")' in recepcionar
    assert 'addItem("Orden de Compra / PO", "PO")' in recepcionar
    assert 'addItem("Transferencia", "TRANSFER")' in recepcionar
    assert "_transfer_receipt_panel" in recepcionar


def test_phase8_transferencia_no_duplica_inventario_en_selector():
    method = _method_source("modulos/recepcion_qr_widget.py", "_on_recepcion_origen_changed")
    assert '"TRANSFER": 2' in method
    assert "add_stock" not in method
    assert "register_purchase" not in method
    assert "registrar_lote" not in method


def test_guard_cubre_variantes_oc_y_recibir_orden():
    for rel_path in ("modulos/recepcion_qr_widget.py", "modulos/compras_pro.py"):
        method = _method_source(rel_path, "_remove_accidental_po_tabs")
        assert "recepcion oc" in method
        assert "recibir orden" in method
