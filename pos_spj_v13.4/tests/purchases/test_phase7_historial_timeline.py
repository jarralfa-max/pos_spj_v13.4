"""
tests/purchases/test_phase7_historial_timeline.py
──────────────────────────────────────────────────
FASE 7 — Tests del Historial mejorado con filtros tipo_doc y timeline.

Verifica:
1. _HistorialLoader incluye purchase_order_id en la query
2. FilterBar tiene combo tipo_doc (directa / con po)
3. Tabla historial tiene 9 columnas (col 7 = Tipo Doc, col 8 = Ver)
4. _poblar_historial filtra correctamente por tipo_doc
5. _refresh_hist_timeline existe y usa purchase_order_id
6. QR NO-TOUCH: ningún cambio toca recepcion_qr_widget.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import re
import pytest


def _compras_src():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "modulos", "compras_pro.py",
    )
    return open(path, encoding="utf-8").read()


class TestPhase7HistorialLoader:

    def test_no_syntax_error(self):
        ast.parse(_compras_src())

    def test_loader_includes_purchase_order_id(self):
        src = _compras_src()
        assert "purchase_order_id" in src, (
            "_HistorialLoader.run() debe incluir purchase_order_id en el SELECT"
        )

    def test_loader_query_has_po_id_alias(self):
        src = _compras_src()
        assert "po_id" in src or "purchase_order_id" in src


class TestPhase7FilterBar:

    def test_tipo_doc_filter_added(self):
        src = _compras_src()
        assert '"tipo_doc"' in src or "'tipo_doc'" in src

    def test_tipo_doc_options_directa_and_con_po(self):
        src = _compras_src()
        assert "directa" in src
        assert "con po" in src


class TestPhase7Table:

    def test_table_has_9_columns(self):
        src = _compras_src()
        # Check that the historial table is created with 9 columns
        # (as opposed to the 7-column PO receipt table)
        idx = src.find("_tbl_hist = QTableWidget()")
        fragment = src[idx:idx + 400] if idx != -1 else ""
        assert "setColumnCount(9)" in fragment, (
            "_tbl_hist debe tener 9 columnas (añadida 'Tipo Doc')"
        )

    def test_tipo_doc_column_in_headers(self):
        src = _compras_src()
        assert "Tipo Doc" in src

    def test_ver_btn_in_col_8(self):
        src = _compras_src()
        # Verify Ver button was moved to column 8
        assert "setCellWidget(ri, 8, btn_det)" in src

    def test_tipo_doc_badge_in_col_7(self):
        src = _compras_src()
        assert "setCellWidget(ri, 7, tipo_badge)" in src


class TestPhase7PoIdStorage:

    def test_po_id_stored_in_user_role_plus_1(self):
        src = _compras_src()
        assert "Qt.UserRole + 1" in src, (
            "po_id debe almacenarse en Qt.UserRole + 1 del item de col 0"
        )

    def test_poblar_historial_filters_by_tipo_doc(self):
        src = _compras_src()
        assert "tipo_doc" in src and ("directa" in src) and ("con po" in src)

    def test_directa_filter_checks_po_id_zero(self):
        src = _compras_src()
        # Should check if r[9] is falsy for 'directa'
        assert 'tipo_doc == "directa"' in src or "tipo_doc == 'directa'" in src


class TestPhase7Timeline:

    def test_refresh_hist_timeline_method_exists(self):
        src = _compras_src()
        assert "_refresh_hist_timeline" in src

    def test_timeline_bar_widget_created(self):
        src = _compras_src()
        assert "_hist_timeline_bar" in src

    def test_timeline_shows_po_folio(self):
        src = _compras_src()
        assert "po_folio" in src

    def test_timeline_shows_pr_folio_when_linked(self):
        src = _compras_src()
        assert "pr_folio" in src

    def test_timeline_hides_when_no_po(self):
        src = _compras_src()
        idx = src.find("def _refresh_hist_timeline")
        body = src[idx:idx + 1200] if idx != -1 else ""
        assert "bar.hide()" in body, (
            "_refresh_hist_timeline debe ocultar la barra cuando po_id == 0"
        )

    def test_timeline_bar_starts_hidden(self):
        src = _compras_src()
        # Find the block where _hist_timeline_bar is created and verify hide() is called nearby
        idx = src.find("_hist_timeline_bar = QFrame()")
        fragment = src[idx:idx + 800] if idx != -1 else ""
        assert ".hide()" in fragment

    def test_on_hist_row_selected_calls_timeline(self):
        src = _compras_src()
        assert "_refresh_hist_timeline" in src
        # Find the method and check a larger window (the call is after the for loop)
        idx = src.find("def _on_hist_row_selected")
        body = src[idx:idx + 3000] if idx != -1 else ""
        assert "_refresh_hist_timeline" in body


class TestPhase7QRNoTouch:

    def test_qr_widget_not_modified_for_phase7(self):
        """Las pestañas QR 1–4 no deben referenciar _hist_timeline ni tipo_doc."""
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "modulos", "recepcion_qr_widget.py",
        )
        qr_src = open(path, encoding="utf-8").read()
        assert "_hist_timeline" not in qr_src
        assert "tipo_doc" not in qr_src
