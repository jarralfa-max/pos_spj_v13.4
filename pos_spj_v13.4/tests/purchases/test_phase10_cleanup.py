"""
Phase 10 characterization tests — Cleanup: filtro Estado PO en historial,
CSV mejorado, auditoría ProcesarCompraUC, DEC-007 actualizado.
"""
import ast
import re
import os
import pytest

COMPRAS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "modulos", "compras_pro.py"
)
DEC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "refactor",
    "compras_documental_decisions.md",
)
SCOPE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "refactor", "compras_scope.md",
)
APP_CONTAINER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "core", "app_container.py",
)


def _src() -> str:
    return open(COMPRAS_PATH).read()


def _dec() -> str:
    return open(DEC_PATH).read()


def _scope() -> str:
    return open(SCOPE_PATH).read()


# ---------------------------------------------------------------------------
# Sintaxis
# ---------------------------------------------------------------------------
class TestSyntax:
    def test_compras_pro_no_syntax_error(self):
        ast.parse(_src())


# ---------------------------------------------------------------------------
# _HistorialLoader — consulta incluye po_estado (col 10)
# ---------------------------------------------------------------------------
class TestHistorialLoader:
    def _loader_body(self) -> str:
        src = _src()
        m = re.search(r"class _HistorialLoader.*?(?=\nclass |\Z)", src, re.DOTALL)
        assert m, "_HistorialLoader class not found"
        return m.group(0)

    def test_query_includes_po_estado(self):
        body = self._loader_body()
        assert "po_estado" in body or "oc.estado" in body

    def test_query_joins_ordenes_compra(self):
        body = self._loader_body()
        assert "ordenes_compra" in body
        assert "LEFT JOIN" in body.upper()

    def test_query_still_has_po_id(self):
        """Backward compat: po_id (col 9) must still be present."""
        body = self._loader_body()
        assert "po_id" in body or "purchase_order_id" in body

    def test_query_uses_coalesce_for_safety(self):
        body = self._loader_body()
        assert "COALESCE" in body.upper()


# ---------------------------------------------------------------------------
# FilterBar en historial — tiene combo po_estado
# ---------------------------------------------------------------------------
class TestFilterBarPOEstado:
    def _build_hist_body(self) -> str:
        src = _src()
        m = re.search(r"def _build_tab_historial.*?(?=\n    def )", src, re.DOTALL)
        assert m
        return m.group(0)

    def test_filter_bar_has_po_estado_key(self):
        body = self._build_hist_body()
        assert '"po_estado"' in body or "'po_estado'" in body

    def test_filter_bar_po_estado_has_abierta(self):
        body = self._build_hist_body()
        assert "ABIERTA" in body

    def test_filter_bar_po_estado_has_parcial(self):
        body = self._build_hist_body()
        assert "PARCIAL" in body

    def test_filter_bar_po_estado_has_recibida(self):
        body = self._build_hist_body()
        assert "RECIBIDA" in body


# ---------------------------------------------------------------------------
# _poblar_historial — aplica filtro po_estado
# ---------------------------------------------------------------------------
class TestPoblarHistorialPOFilter:
    def _poblar_body(self) -> str:
        src = _src()
        m = re.search(r"def _poblar_historial.*?(?=\n    def )", src, re.DOTALL)
        assert m
        return m.group(0)

    def test_extracts_po_estado_from_row(self):
        body = self._poblar_body()
        # r[10] for po_estado
        assert "r[10]" in body

    def test_applies_po_estado_filter(self):
        body = self._poblar_body()
        assert "po_estado" in body

    def test_safe_len_check_for_col10(self):
        body = self._poblar_body()
        assert "len(r) > 10" in body

    def test_stores_po_estado_in_user_role_2(self):
        body = self._poblar_body()
        assert "UserRole + 2" in body or "UserRole+2" in body

    def test_tooltip_includes_po_estado(self):
        body = self._poblar_body()
        assert "po_estado" in body


# ---------------------------------------------------------------------------
# _exportar_historial_csv — usa _hist_all_rows, incluye todas las columnas
# ---------------------------------------------------------------------------
class TestExportCSV:
    def _export_body(self) -> str:
        src = _src()
        m = re.search(r"def _exportar_historial_csv.*?(?=\n    def |\Z)", src, re.DOTALL)
        assert m
        return m.group(0)

    def test_uses_hist_all_rows_cache(self):
        body = self._export_body()
        assert "_hist_all_rows" in body

    def test_applies_active_filters(self):
        body = self._export_body()
        assert "hist_filter" in body
        assert "filtros" in body

    def test_headers_include_tipo_doc(self):
        body = self._export_body()
        assert "Tipo Doc" in body

    def test_headers_include_estado_po(self):
        body = self._export_body()
        assert "Estado PO" in body or "po_estado" in body.lower()

    def test_exports_po_id_column(self):
        body = self._export_body()
        assert "po_id" in body or "PO #" in body

    def test_applies_po_estado_filter_in_export(self):
        """Export aplica el mismo filtro po_estado que el historial."""
        body = self._export_body()
        assert "po_est" in body or "po_estado" in body

    def test_respects_ocultar_totales(self):
        body = self._export_body()
        assert "ocultar_totales" in body

    def test_uses_utf8_bom_encoding(self):
        """utf-8-sig para compatibilidad con Excel."""
        body = self._export_body()
        assert "utf-8-sig" in body

    def test_shows_record_count_in_toast(self):
        body = self._export_body()
        assert "registros" in body or "len(rows)" in body


# ---------------------------------------------------------------------------
# Auditoría ProcesarCompraUC — DEC-007 actualizado
# ---------------------------------------------------------------------------
class TestDEC007Audit:
    def test_dec007_has_audit_findings(self):
        doc = _dec()
        assert "Auditoría Fase 10" in doc or "2026-05-16" in doc

    def test_dec007_lists_app_container_reference(self):
        doc = _dec()
        assert "app_container" in doc

    def test_dec007_marked_blocked(self):
        doc = _dec()
        assert "BLOCKED" in doc or "bloqueado" in doc.lower()

    def test_dec007_has_action_plan(self):
        doc = _dec()
        assert "RegistrarCompraUC" in doc or "TraditionalPurchaseUC" in doc

    def test_procesar_compra_uc_still_importable(self):
        """DEC-007: UC existe pero no se eliminó."""
        from core.use_cases.compra import ProcesarCompraUC
        assert ProcesarCompraUC is not None

    def test_procesar_compra_uc_not_used_in_toolbar(self):
        src = _src()
        m = re.search(
            r"def _build_documental_toolbar.*?(?=\n    def _build_provider_sidebar)",
            src, re.DOTALL
        )
        assert m
        assert "ProcesarCompraUC" not in m.group(0)

    def test_procesar_compra_uc_not_used_in_new_actions(self):
        src = _src()
        for method in ["_accion_aprobar_pr", "_accion_rechazar_pr",
                       "_accion_convertir_a_po", "_accion_enviar_recepcion_doc"]:
            m = re.search(rf"def {method}.*?(?=\n    def |\Z)", src, re.DOTALL)
            if m:
                assert "ProcesarCompraUC" not in m.group(0), \
                    f"ProcesarCompraUC used in {method}"


# ---------------------------------------------------------------------------
# compras_scope.md — fases 8, 9, 10 marcadas ✅
# ---------------------------------------------------------------------------
class TestScopeDoc:
    def test_fase8_marked_complete(self):
        scope = _scope()
        assert "| 8 | UI Toolbar Documental | ✅" in scope

    def test_fase9_marked_complete(self):
        scope = _scope()
        assert "| 9 | UI QR mejorada | ✅" in scope

    def test_fase10_marked_complete(self):
        scope = _scope()
        assert "| **10**" in scope and "✅" in scope

    def test_acceptance_criteria_updated(self):
        scope = _scope()
        assert "363+" in scope or "Filtro Estado PO" in scope

    def test_dec007_audit_referenced_in_scope(self):
        scope = _scope()
        assert "ProcesarCompraUC" in scope or "DEC-007" in scope


# ---------------------------------------------------------------------------
# No regresión: suite existente no rota
# ---------------------------------------------------------------------------
class TestNoRegression:
    def test_hist_filter_still_has_estado(self):
        src = _src()
        m = re.search(r"def _build_tab_historial.*?(?=\n    def )", src, re.DOTALL)
        assert m
        body = m.group(0)
        assert '"estado"' in body

    def test_hist_filter_still_has_tipo_doc(self):
        src = _src()
        m = re.search(r"def _build_tab_historial.*?(?=\n    def )", src, re.DOTALL)
        assert m
        assert '"tipo_doc"' in m.group(0)

    def test_poblar_historial_still_filters_tipo_doc(self):
        src = _src()
        m = re.search(r"def _poblar_historial.*?(?=\n    def )", src, re.DOTALL)
        assert m
        body = m.group(0)
        assert "tipo_doc" in body
        assert "con po" in body or "con_po" in body

    def test_tbl_hist_still_9_columns(self):
        src = _src()
        assert "setColumnCount(9)" in src

    def test_export_btn_still_connected(self):
        src = _src()
        assert "_exportar_historial_csv" in src
        assert "btn_export" in src
