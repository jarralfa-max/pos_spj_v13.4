"""
tests/purchases/test_phase6_reception_po_ui.py
───────────────────────────────────────────────
FASE 2/6 — Tests del submodo de recepción de orden en RecepcionQRWidget.

Verifica:
1. No existe pestaña separada para PO.
2. El panel interno de recepción de orden conserva los métodos existentes.
3. _build_po_reception_panel llama a ReceivePOAdapter (no reimplementa inventario).
4. QR NO-TOUCH: las 4 pestañas originales se mantienen.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import pytest


def _src():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "modulos", "recepcion_qr_widget.py",
    )
    return open(path, encoding="utf-8").read()


def _method_source(src: str, method_name: str) -> str:
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"Método {method_name} no encontrado")


class TestPhase6SourceCode:

    def test_no_syntax_error(self):
        ast.parse(_src())

    def test_no_tab_po_recv_added_to_build_ui(self):
        src = _src()
        build_ui = _method_source(src, "_build_ui")
        assert build_ui.count(".addTab(") == 4
        assert "_tab_po_recv" not in build_ui
        assert "Recepción PO" not in build_ui

    def test_build_po_reception_panel_method_exists(self):
        assert "_build_po_reception_panel" in _src()

    def test_cargar_pos_abiertas_exists(self):
        assert "_cargar_pos_abiertas" in _src()

    def test_cargar_lineas_po_exists(self):
        assert "_cargar_lineas_po" in _src()

    def test_aceptar_todo_po_exists(self):
        assert "_aceptar_todo_po" in _src()

    def test_confirmar_recepcion_po_exists(self):
        assert "_confirmar_recepcion_po" in _src()

    def test_uses_receive_po_adapter(self):
        src = _src()
        assert "receive_po_adapter" in src
        assert "register_partial_receipt" in src

    def test_uses_get_po_lines(self):
        assert "get_po_lines" in _src()

    def test_does_not_call_add_stock_directly(self):
        """Phase 6 UI no llama add_stock directamente — delega al adapter."""
        src = _src()
        # Find only the integrated PO section
        start = src.find("# ── Submodo interno: recepción de Orden de Compra")
        end   = src.find("# ── Nuevos helpers UI", start)
        phase6 = src[start:end] if start != -1 and end != -1 else src
        assert "add_stock" not in phase6, (
            "La pestaña Phase 6 no debe llamar add_stock directamente"
        )

    def test_does_not_reimport_qr_service(self):
        """Phase 6 no importa qr_service (QR NO-TOUCH policy)."""
        src = _src()
        start = src.find("# ── Submodo interno: recepción de Orden de Compra")
        end   = src.find("# ── Nuevos helpers UI", start)
        phase6 = src[start:end] if start != -1 else ""
        assert "qr_service" not in phase6

    def test_original_qr_tabs_still_present(self):
        """Las 4 tabs originales del widget QR siguen presentes."""
        src = _src()
        assert "🏷️ 1. Generar Etiqueta QR" in src
        assert "📋 2. Asignar Compra" in src
        assert "📦 3. Recepcionar" in src
        assert "📜 Historial" in src

    def test_phase2_integrated_po_as_submode_not_fifth_tab(self):
        """Fase 2 reintegra PO como submodo: total debe ser 4 tabs internas."""
        src = _src()
        build_ui = _method_source(src, "_build_ui")
        assert build_ui.count(".addTab(") == 4
        assert "_po_receipt_panel" in src
        assert "_tab_po_recv" not in src

    def test_build_tab_generar_unchanged(self):
        """_build_tab_generar no debe referenciar _po_id_activo ni receive_po_adapter."""
        src = _src()
        start = src.find("def _build_tab_generar(")
        end   = src.find("\n    def ", start + 1)
        body  = src[start:end]
        assert "_po_id_activo" not in body
        assert "receive_po_adapter" not in body

    def test_build_tab_recepcionar_unchanged(self):
        """_build_tab_recepcionar no debe referenciar _po_id_activo."""
        src = _src()
        start = src.find("def _build_tab_recepcionar(")
        end   = src.find("\n    def ", start + 1)
        body  = src[start:end]
        assert "_po_id_activo" not in body

    def test_confirmar_recepcion_po_uses_receipt_item(self):
        src = _src()
        assert "ReceiptItem" in src

    def test_table_has_8_columns(self):
        src = _src()
        assert "setColumnCount(8)" in src


class TestReceivePOAdapterContractPhase6:
    """
    Verifica que ReceivePOAdapter sigue satisfaciendo el contrato
    que la UI Phase 6 espera.
    """

    def test_adapter_has_get_po_lines(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert hasattr(ReceivePOAdapter, 'get_po_lines')

    def test_adapter_has_get_po_status(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert hasattr(ReceivePOAdapter, 'get_po_status')

    def test_adapter_has_register_partial_receipt(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert hasattr(ReceivePOAdapter, 'register_partial_receipt')

    def test_receipt_item_has_required_fields(self):
        from application.purchases.receive_po_adapter import ReceiptItem
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ReceiptItem)}
        assert {'product_id', 'qty_received', 'unit_cost', 'nombre'} <= fields

    def test_receipt_result_has_po_estado_and_completion(self):
        from application.purchases.receive_po_adapter import ReceiptResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ReceiptResult)}
        assert {'ok', 'po_estado', 'completion', 'folio', 'warnings', 'error'} <= fields
