"""
tests/purchases/test_fase9_historial_documental.py
───────────────────────────────────────────────────
FASE 9 — Historial documental completo.

Verifica (sin instanciar PyQt5):
1. _refresh_hist_timeline() no contiene SQL directo (AST)
2. Timeline tiene nodos: PR, APROBACIÓN, PO, RECEPCIÓN, CXP (AST)
3. _node helper usa Colors.* (no hex hardcodeado) (AST)
4. Datos fetched via repo solo (getattr container, no db.execute) (AST)
5. _actualizar_hist_kpi_sidebar() llamada desde _poblar_historial (AST)
6. _exportar_historial_csv() existe y exporta los campos esperados (AST)
7. FilterBar en tab historial tiene estado + tipo_doc + po_estado filtros (AST)
8. _build_hist_kpi_sidebar() construye atributos de KPI necesarios (AST)
9. No colores hardcodeados en métodos nuevos/modificados FASE 9
"""
from __future__ import annotations

import ast
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── Helpers ───────────────────────────────────────────────────────────────────

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
                if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name):
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


# ── 1. No SQL in _refresh_hist_timeline ──────────────────────────────────────

class TestTimelineNoSQL:
    """_refresh_hist_timeline() must not contain SQL — data via repo only."""

    def _src(self) -> str:
        src = _method_src("_refresh_hist_timeline")
        assert src is not None, "_refresh_hist_timeline not found"
        return src

    def test_method_exists(self):
        assert _method_src("_refresh_hist_timeline") is not None

    def test_no_db_execute(self):
        src = self._src()
        assert "db.execute" not in src, (
            "_refresh_hist_timeline no debe llamar db.execute. "
            "Los datos de PO y PR se obtienen via repos."
        )

    def test_no_raw_select(self):
        src = self._src()
        assert not re.search(r'\bSELECT\s+\w', src, re.IGNORECASE), (
            "_refresh_hist_timeline no debe tener SQL SELECT inline."
        )

    def test_no_fetchone(self):
        src = self._src()
        assert ".fetchone()" not in src, (
            "_refresh_hist_timeline no debe llamar .fetchone() — usa el repo."
        )

    def test_uses_purchase_order_repo(self):
        src = self._src()
        assert "purchase_order_repo" in src, (
            "_refresh_hist_timeline debe obtener la PO desde purchase_order_repo."
        )

    def test_uses_purchase_request_repo(self):
        src = self._src()
        assert "purchase_request_repo" in src, (
            "_refresh_hist_timeline debe obtener la PR desde purchase_request_repo."
        )

    def test_repos_accessed_via_getattr(self):
        """Repos deben obtenerse con getattr(container, ..., None) para degradar gracefully."""
        src = self._src()
        assert "getattr(self.container" in src, (
            "_refresh_hist_timeline debe usar getattr(self.container, 'repo', None) "
            "para degradar gracefully si el repo no está disponible."
        )

    def test_graceful_degrade_when_po_not_found(self):
        """Debe manejar po is None sin crashear (muestra nodo mínimo)."""
        src = self._src()
        assert "po is None" in src or "if po is None" in src or "if not po" in src, (
            "_refresh_hist_timeline debe verificar si po es None y degradar gracefully."
        )


# ── 2. Timeline nodes present ─────────────────────────────────────────────────

class TestTimelineNodesPresent:
    """Timeline debe mostrar todos los nodos del ciclo documental."""

    def _src(self) -> str:
        return _method_src("_refresh_hist_timeline")

    def test_pr_node_present(self):
        src = self._src()
        assert "📋" in src or "pr_folio" in src, (
            "Timeline debe incluir nodo PR cuando existe PR vinculada."
        )

    def test_aprobacion_node_present(self):
        src = self._src()
        assert "Aprobada" in src or "aprobado_por" in src, (
            "Timeline debe incluir nodo APROBACIÓN cuando PR tiene aprobado_por."
        )

    def test_po_node_present(self):
        src = self._src()
        assert "📦" in src or "po_folio" in src, (
            "Timeline debe incluir nodo PO."
        )

    def test_recepcion_node_present(self):
        src = self._src()
        assert "📥" in src or "Recepción" in src or "recepcion" in src.lower(), (
            "Timeline debe incluir nodo RECEPCIÓN que refleja el estado de entrega."
        )

    def test_compra_node_present(self):
        src = self._src()
        assert "🛒" in src or "Compra registrada" in src or "compra_folio" in src, (
            "Timeline debe incluir nodo de Compra registrada."
        )

    def test_cxp_node_present(self):
        src = self._src()
        assert "💳" in src or "CXP" in src, (
            "Timeline debe incluir nodo CXP (Cuentas por Pagar) como indicador de ciclo."
        )

    def test_recepcion_shows_parcial_state(self):
        """Debe distinguir entre recepción parcial y completa."""
        src = self._src()
        assert "parcial" in src.lower() or "PARCIAL" in src, (
            "Timeline debe indicar recepción parcial cuando PO.estado=PARCIAL."
        )

    def test_recepcion_shows_completa_state(self):
        """Debe marcar recepción como completa cuando PO.estado=RECIBIDA."""
        src = self._src()
        assert "RECIBIDA" in src or "recibida" in src.lower(), (
            "Timeline debe marcar recepción como completa para PO en estado RECIBIDA."
        )


# ── 3. Design tokens — no hardcoded hex in _refresh_hist_timeline ────────────

class TestTimelineNoHardcodedColors:
    """_refresh_hist_timeline debe usar Colors.* tokens, no hex literals."""

    def _src(self) -> str:
        return _method_src("_refresh_hist_timeline")

    def test_no_hardcoded_eff6ff(self):
        """#EFF6FF era el bg hardcodeado del nodo 'primary'. Debe usar Colors.*."""
        src = self._src()
        assert "#EFF6FF" not in src and "#eff6ff" not in src, (
            "_refresh_hist_timeline no debe usar #EFF6FF hardcodeado. "
            "Usar Colors.PRIMARY_BASE con opacidad o Colors.NEUTRAL.*."
        )

    def test_no_hardcoded_f0fdf4(self):
        """#F0FDF4 era el bg hardcodeado del nodo 'success'. Debe usar Colors.*."""
        src = self._src()
        assert "#F0FDF4" not in src and "#f0fdf4" not in src, (
            "_refresh_hist_timeline no debe usar #F0FDF4 hardcodeado. "
            "Usar Colors.SUCCESS_BASE con opacidad."
        )

    def test_no_hardcoded_bfdbfe(self):
        """#BFDBFE era el border hardcodeado del nodo 'primary'."""
        src = self._src()
        assert "#BFDBFE" not in src and "#bfdbfe" not in src

    def test_no_hardcoded_bbf7d0(self):
        """#BBF7D0 era el border hardcodeado del nodo 'success'."""
        src = self._src()
        assert "#BBF7D0" not in src and "#bbf7d0" not in src

    def test_uses_success_base(self):
        src = self._src()
        assert "Colors.SUCCESS_BASE" in src, (
            "_refresh_hist_timeline debe usar Colors.SUCCESS_BASE para nodos completados."
        )

    def test_uses_primary_base(self):
        src = self._src()
        assert "Colors.PRIMARY_BASE" in src, (
            "_refresh_hist_timeline debe usar Colors.PRIMARY_BASE para nodos activos."
        )

    def test_uses_slate_tokens(self):
        src = self._src()
        assert "Colors.NEUTRAL.SLATE_" in src, (
            "_refresh_hist_timeline debe usar Colors.NEUTRAL.SLATE_* para nodos pendientes."
        )


# ── 4. KPI sidebar is called from _poblar_historial ──────────────────────────

class TestKPISidebarWiring:
    """_actualizar_hist_kpi_sidebar() debe llamarse desde _poblar_historial()."""

    def test_kpi_sidebar_called_from_poblar(self):
        src = _method_src("_poblar_historial")
        assert src is not None
        assert "_actualizar_hist_kpi_sidebar" in src, (
            "_poblar_historial debe llamar _actualizar_hist_kpi_sidebar() "
            "para actualizar el panel de KPIs cada vez que se cargan datos."
        )

    def test_kpi_sidebar_method_exists(self):
        assert _method_src("_actualizar_hist_kpi_sidebar") is not None

    def test_kpi_sidebar_uses_repo_for_monthly(self):
        """Los KPIs mensuales se deben obtener via _purchase_repo, no SQL directo."""
        src = _method_src("_actualizar_hist_kpi_sidebar")
        assert src is not None
        assert "_purchase_repo" in src or "purchase_repo" in src, (
            "_actualizar_hist_kpi_sidebar debe usar self._purchase_repo para KPIs mensuales."
        )
        assert not re.search(r'\bSELECT\b.*\bFROM\b', src, re.IGNORECASE | re.DOTALL), (
            "_actualizar_hist_kpi_sidebar no debe tener SQL directo."
        )

    def test_kpi_total_periodo_attr_exists(self):
        """_build_hist_kpi_sidebar debe crear self._kpi_total_periodo."""
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        assert "_kpi_total_periodo" in src

    def test_kpi_num_compras_attr_exists(self):
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        assert "_kpi_num_compras" in src

    def test_kpi_completadas_attr_exists(self):
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        assert "_kpi_completadas" in src

    def test_kpi_alertas_attr_exists(self):
        src = _method_src("_build_hist_kpi_sidebar")
        assert src is not None
        assert "_kpi_alertas_lbl" in src


# ── 5. Export CSV exists and has correct headers ──────────────────────────────

class TestExportCSV:
    """_exportar_historial_csv() debe exportar los campos correctos."""

    def _src(self) -> str:
        src = _method_src("_exportar_historial_csv")
        assert src is not None, "_exportar_historial_csv not found"
        return src

    def test_method_exists(self):
        assert _method_src("_exportar_historial_csv") is not None

    def test_uses_hist_all_rows_cache(self):
        """Debe leer del cache _hist_all_rows (no re-query DB)."""
        src = self._src()
        assert "_hist_all_rows" in src, (
            "_exportar_historial_csv debe leer de _hist_all_rows para evitar re-query."
        )

    def test_writes_folio_column(self):
        src = self._src()
        assert "Folio" in src

    def test_writes_proveedor_column(self):
        src = self._src()
        assert "Proveedor" in src

    def test_writes_estado_column(self):
        src = self._src()
        assert "Estado" in src

    def test_writes_tipo_doc_column(self):
        src = self._src()
        assert "Tipo Doc" in src

    def test_writes_po_estado_column(self):
        src = self._src()
        assert "Estado PO" in src or "po_estado" in src.lower()

    def test_applies_active_filters(self):
        """Debe aplicar los mismos filtros que _poblar_historial."""
        src = self._src()
        assert "_hist_filter" in src, (
            "_exportar_historial_csv debe aplicar los filtros activos de _hist_filter."
        )

    def test_uses_csv_writer(self):
        src = self._src()
        assert "csv.writer" in src or "writer.writerow" in src


# ── 6. FilterBar has expected filter fields ───────────────────────────────────

class TestHistFilterBar:
    """Tab historial debe tener FilterBar con estado, tipo_doc y po_estado filtros."""

    def _src(self) -> str:
        src = _method_src("_build_tab_historial")
        assert src is not None, "_build_tab_historial not found"
        return src

    def test_filterbar_has_estado(self):
        src = self._src()
        assert '"estado"' in src or "'estado'" in src, (
            "_build_tab_historial FilterBar debe tener filtro 'estado'."
        )

    def test_filterbar_has_tipo_doc(self):
        src = self._src()
        assert '"tipo_doc"' in src or "'tipo_doc'" in src, (
            "_build_tab_historial FilterBar debe tener filtro 'tipo_doc' (Directa/Con PO)."
        )

    def test_filterbar_has_po_estado(self):
        src = self._src()
        assert '"po_estado"' in src or "'po_estado'" in src, (
            "_build_tab_historial FilterBar debe tener filtro 'po_estado' (ABIERTA/PARCIAL/RECIBIDA)."
        )

    def test_has_date_range_pickers(self):
        src = self._src()
        assert "_hist_desde" in src and "_hist_hasta" in src, (
            "_build_tab_historial debe tener pickers de fecha _hist_desde y _hist_hasta."
        )

    def test_has_export_csv_button(self):
        src = self._src()
        assert "_exportar_historial_csv" in src or "exportar" in src.lower(), (
            "_build_tab_historial debe conectar botón de exportar CSV."
        )

    def test_has_kpi_sidebar(self):
        src = self._src()
        assert "_build_hist_kpi_sidebar" in src, (
            "_build_tab_historial debe incluir el sidebar de KPIs."
        )


# ── 7. No banned colors in FASE 9 modified methods ───────────────────────────

class TestNoBannedColorsInFase9Methods:

    @pytest.mark.parametrize("method_name", [
        "_refresh_hist_timeline",
        "_build_hist_kpi_sidebar",
        "_actualizar_hist_kpi_sidebar",
    ])
    def test_no_background_white(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        offenses = [
            l.strip() for l in src.splitlines()
            if re.search(r'background\s*:\s*white\b', l, re.IGNORECASE)
        ]
        assert not offenses, f"background:white en {method_name}: {offenses}"

    @pytest.mark.parametrize("method_name", [
        "_refresh_hist_timeline",
        "_build_hist_kpi_sidebar",
        "_actualizar_hist_kpi_sidebar",
    ])
    def test_no_slate50_as_background(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        offenses = []
        for line in src.splitlines():
            stripped = line.strip()
            if not re.search(r'\bSLATE_50\b', stripped):
                continue
            if "background" not in stripped:
                continue
            if "background:transparent" in stripped or "background: transparent" in stripped:
                continue
            offenses.append(stripped)
        assert not offenses, f"SLATE_50 como background en {method_name}: {offenses}"


# ── 8. _cargar_historial_compras uses async loader (no blocking SQL) ──────────

class TestHistorialLoaderPattern:
    """_cargar_historial_compras debe usar _HistorialLoader thread, no SQL inline."""

    def test_method_exists(self):
        assert _method_src("_cargar_historial_compras") is not None

    def test_uses_hist_loader(self):
        src = _method_src("_cargar_historial_compras")
        assert src is not None
        assert "_HistorialLoader" in src or "_hist_loader" in src, (
            "_cargar_historial_compras debe usar _HistorialLoader para carga asíncrona."
        )

    def test_no_inline_sql(self):
        src = _method_src("_cargar_historial_compras")
        assert src is not None
        assert not re.search(r'\bSELECT\s+\w', src, re.IGNORECASE), (
            "_cargar_historial_compras no debe tener SQL inline — delegarlo a _HistorialLoader."
        )

    def test_connects_to_poblar(self):
        src = _method_src("_cargar_historial_compras")
        assert src is not None
        assert "_poblar_historial" in src, (
            "_cargar_historial_compras debe conectar la señal loaded a _poblar_historial."
        )
