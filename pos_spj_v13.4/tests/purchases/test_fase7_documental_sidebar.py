"""
tests/purchases/test_fase7_documental_sidebar.py
──────────────────────────────────────────────────
FASE 7 — PR / Aprobación / PO en Compra Tradicional.

Verifica (sin instanciar PyQt5):
1. Sidebar izquierda: _build_documental_toolbar() estructura completa
2. _cargar_docs_erp() usa UC-first con fallback documentado
3. Botón "Aprobar PR" delega a PurchaseRequestUC.aprobar()
4. Botón "Rechazar PR" delega a PurchaseRequestUC.rechazar()
5. Botón "Convertir a PO" delega a PurchaseRequestUC.convertir_a_po()
6. _refresh_stepper_for_doc() mapea estados a pasos correctamente (AST)
7. _on_doc_item_clicked() llama _refresh_stepper_for_doc() (AST)
8. PurchaseRequestUC state machine (integración con SQLite in-memory)
9. No hay SQL directo en flujos principales (delegación a UC)
10. No colores prohibidos en métodos nuevos/modificados

No instancia PyQt5.
"""
from __future__ import annotations

import ast
import os
import re
import sqlite3
import sys
from unittest.mock import MagicMock, patch

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
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


def _make_pr_db() -> sqlite3.Connection:
    """Minimal in-memory DB with purchase_requests + items tables."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            proveedor_id INTEGER DEFAULT 0,
            proveedor_nombre TEXT DEFAULT '',
            sucursal_id INTEGER DEFAULT 1,
            usuario TEXT DEFAULT 'test',
            subtotal REAL DEFAULT 0,
            iva_monto REAL DEFAULT 0,
            total REAL DEFAULT 0,
            metodo_pago TEXT DEFAULT 'CONTADO',
            condicion_pago TEXT DEFAULT 'liquidado',
            plazo_dias INTEGER DEFAULT 0,
            moneda TEXT DEFAULT 'MXN',
            notas TEXT DEFAULT '',
            doc_ref TEXT DEFAULT '',
            estado TEXT DEFAULT 'BORRADOR',
            aprobado_por TEXT,
            fecha_aprobacion TEXT,
            rechazado_por TEXT,
            motivo_rechazo TEXT,
            fecha_creacion TEXT DEFAULT (datetime('now')),
            fecha_actualizacion TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS purchase_request_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id INTEGER,
            producto_id INTEGER,
            nombre TEXT DEFAULT '',
            cantidad REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg',
            precio_unitario REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            lote TEXT DEFAULT '',
            fecha_caducidad TEXT,
            notas TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ordenes_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            pr_id INTEGER,
            proveedor_id INTEGER,
            proveedor_nombre TEXT,
            sucursal_id INTEGER DEFAULT 1,
            usuario TEXT,
            subtotal REAL DEFAULT 0,
            iva_monto REAL DEFAULT 0,
            total REAL DEFAULT 0,
            metodo_pago TEXT DEFAULT 'CONTADO',
            condicion_pago TEXT DEFAULT 'liquidado',
            plazo_dias INTEGER DEFAULT 0,
            moneda TEXT DEFAULT 'MXN',
            notas TEXT DEFAULT '',
            doc_ref TEXT DEFAULT '',
            fecha_entrega_esperada TEXT,
            estado TEXT DEFAULT 'ABIERTA',
            fecha_creacion TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ordenes_compra_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_id INTEGER,
            producto_id INTEGER,
            nombre TEXT DEFAULT '',
            cantidad REAL DEFAULT 0,
            recibido REAL DEFAULT 0,
            precio_unitario REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg',
            lote TEXT DEFAULT '',
            fecha_caducidad TEXT,
            notas TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT, accion TEXT, entidad TEXT, entidad_id TEXT,
            usuario TEXT, detalles TEXT, before_json TEXT, after_json TEXT,
            sucursal_id INTEGER, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_pr_container(conn):
    """Container stub wired for PR/PO UC tests."""
    from repositories.purchase_request_repository import PurchaseRequestRepository
    from repositories.purchase_order_repository import PurchaseOrderRepository
    container = MagicMock()
    container.db = conn
    container.purchase_request_repo = PurchaseRequestRepository(conn)
    container.purchase_order_repo = PurchaseOrderRepository(conn)
    return container


# ── 1. Sidebar structure (AST) ────────────────────────────────────────────────

class TestDocumentalSidebarStructure:
    """_build_documental_toolbar() has the required UI elements."""

    def _src(self):
        return _method_src("_build_documental_toolbar")

    def test_method_exists(self):
        assert self._src() is not None

    def test_has_doc_erp_list(self):
        assert "_doc_erp_list" in self._src(), (
            "Sidebar debe tener _doc_erp_list (QListWidget de documentos ERP)"
        )

    def test_has_btn_aprobar_pr(self):
        assert "_btn_aprobar_pr" in self._src()

    def test_has_btn_rechazar_pr(self):
        assert "_btn_rechazar_pr" in self._src()

    def test_has_btn_conv_po(self):
        assert "_btn_conv_po" in self._src()

    def test_has_btn_enviar_rec_doc(self):
        assert "_btn_enviar_rec_doc" in self._src()

    def test_has_doc_detail_card(self):
        assert "_doc_detail_card" in self._src()

    def test_has_filter_chips(self):
        assert "_doc_filter_chips" in self._src()

    def test_cargar_docs_erp_triggered_on_build(self):
        """Sidebar debe cargar documentos al construirse (via QTimer)."""
        src = self._src()
        assert "_cargar_docs_erp" in src, (
            "QTimer.singleShot debe llamar _cargar_docs_erp al construirse el sidebar."
        )

    def test_action_buttons_start_disabled(self):
        """Action buttons deben iniciarse deshabilitados hasta que se seleccione un doc."""
        src = self._src()
        assert "setEnabled(False)" in src, (
            "Los botones de acción deben iniciarse deshabilitados."
        )


# ── 2. _cargar_docs_erp UC-first pattern (AST) ───────────────────────────────

class TestCargarDocsERPPattern:
    """_cargar_docs_erp() usa UCs como fuente primaria."""

    def _src(self):
        return _method_src("_cargar_docs_erp")

    def test_method_exists(self):
        assert self._src() is not None

    def test_uses_purchase_request_uc(self):
        assert "PurchaseRequestUC" in self._src(), (
            "_cargar_docs_erp debe intentar usar PurchaseRequestUC primero."
        )

    def test_uses_purchase_order_uc(self):
        assert "PurchaseOrderUC" in self._src(), (
            "_cargar_docs_erp debe intentar usar PurchaseOrderUC para POs."
        )

    def test_calls_poblar_lista_docs(self):
        assert "_poblar_lista_docs" in self._src(), (
            "_cargar_docs_erp debe llamar _poblar_lista_docs para actualizar la UI."
        )

    def test_no_bare_sql_in_primary_path(self):
        """El SQL directo solo debe aparecer dentro de except (fallback) — no en la ruta principal."""
        src = self._src()
        lines = src.splitlines()
        except_depth = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("except"):
                except_depth += 1
            # Primary SQL markers must not appear outside except blocks
            if except_depth == 0 and "SELECT" in line.upper() and "FROM" in line.upper():
                pytest.fail(
                    f"SQL directo fuera de except en _cargar_docs_erp: {stripped}. "
                    f"Debe estar en el bloque except (fallback)."
                )


# ── 3. Action methods delegate to UCs (AST) ──────────────────────────────────

class TestActionMethodsDelegation:
    """Action buttons delegate to PurchaseRequestUC methods."""

    def test_accion_aprobar_pr_uses_uc(self):
        src = _method_src("_accion_aprobar_pr")
        assert src is not None
        assert "PurchaseRequestUC" in src, "_accion_aprobar_pr debe usar PurchaseRequestUC"
        assert ".aprobar(" in src, "_accion_aprobar_pr debe llamar uc.aprobar()"

    def test_accion_aprobar_pr_refreshes_sidebar(self):
        src = _method_src("_accion_aprobar_pr")
        assert "_cargar_docs_erp" in src, (
            "_accion_aprobar_pr debe llamar _cargar_docs_erp() para actualizar el sidebar."
        )

    def test_accion_rechazar_pr_uses_uc(self):
        src = _method_src("_accion_rechazar_pr")
        assert src is not None
        assert "PurchaseRequestUC" in src
        assert ".rechazar(" in src

    def test_accion_rechazar_pr_requires_motivo(self):
        src = _method_src("_accion_rechazar_pr")
        assert "QInputDialog" in src or "motivo" in src, (
            "_accion_rechazar_pr debe pedir motivo antes de rechazar."
        )

    def test_accion_convertir_a_po_uses_uc(self):
        src = _method_src("_accion_convertir_a_po")
        assert src is not None
        assert "PurchaseRequestUC" in src
        assert ".convertir_a_po(" in src

    def test_accion_convertir_a_po_refreshes_sidebar(self):
        src = _method_src("_accion_convertir_a_po")
        assert "_cargar_docs_erp" in src

    def test_procesar_como_pr_sends_to_approval(self):
        src = _method_src("_procesar_como_pr")
        assert src is not None
        assert "PRState.PENDIENTE_APROBACION" in src, (
            "FASE 7: crear solicitud desde Compra Tradicional debe dejarla "
            "pendiente de aprobación, sin afectar inventario."
        )

    def test_accion_editar_doc_has_no_sql_fallback(self):
        src = _method_src("_accion_editar_doc")
        assert src is not None
        assert "db.execute" not in src
        assert not re.search(r'\bSELECT\s+\w', src, re.IGNORECASE)
        assert "get_items" in src or "doc.get('items')" in src

    def test_refresh_doc_acciones_enables_approve_only_for_pending(self):
        src = _method_src("_refresh_doc_acciones")
        assert src is not None
        assert "PENDIENTE_APROBACION" in src, (
            "_refresh_doc_acciones debe habilitar Aprobar solo para PR PENDIENTE_APROBACION."
        )

    def test_refresh_doc_acciones_enables_conv_po_only_for_approved(self):
        src = _method_src("_refresh_doc_acciones")
        assert "APROBADA" in src, (
            "_refresh_doc_acciones debe habilitar Convertir PO solo para PR APROBADA."
        )

    def test_refresh_doc_acciones_has_permission_guard(self):
        src = _method_src("_refresh_doc_acciones")
        assert "_tiene_permiso" in src, (
            "_refresh_doc_acciones debe verificar permisos antes de habilitar aprobación."
        )


# ── 4. _refresh_stepper_for_doc (AST) ────────────────────────────────────────

class TestRefreshStepperForDoc:
    """_refresh_stepper_for_doc() maps document states to stepper steps."""

    def _src(self):
        return _method_src("_refresh_stepper_for_doc")

    def test_method_exists(self):
        assert self._src() is not None, (
            "_refresh_stepper_for_doc debe existir para FASE 7 — "
            "stepper refleja el paso del documento seleccionado."
        )

    def test_has_state_to_step_mapping(self):
        src = self._src()
        assert "BORRADOR" in src
        assert "PENDIENTE_APROBACION" in src
        assert "APROBADA" in src
        assert "CONVERTIDA_A_PO" in src

    def test_handles_po_states(self):
        src = self._src()
        assert "ABIERTA" in src, "Debe mapear estado PO ABIERTA al stepper"

    def test_guards_against_invisible_stepper(self):
        src = self._src()
        assert "isVisible" in src or "_hidden_stepper" in src, (
            "_refresh_stepper_for_doc debe verificar que el stepper es visible."
        )

    def test_applies_done_active_idle_styles(self):
        src = self._src()
        assert "done_style" in src or "done" in src
        assert "active_style" in src or "active" in src
        assert "idle_style" in src or "idle" in src

    def test_uses_design_tokens_not_hardcoded_colors(self):
        src = self._src()
        assert "Colors." in src, "Debe usar tokens de color (Colors.*)"
        assert "background:white" not in src
        assert re.search(r'\bSLATE_50\b', src) is None

    def test_borrador_maps_to_step_0(self):
        """BORRADOR → step 0 (first step)."""
        src = self._src()
        assert '"BORRADOR"' in src or "'BORRADOR'" in src
        borrador_idx = src.find('"BORRADOR"')
        if borrador_idx == -1:
            borrador_idx = src.find("'BORRADOR'")
        block = src[borrador_idx:borrador_idx + 30]
        assert "0" in block, "BORRADOR debe mapearse al paso 0."

    def test_pendiente_maps_to_step_2(self):
        """PENDIENTE_APROBACION → step 2 (Condición — enviado a aprobación)."""
        src = self._src()
        pend_idx = src.find("PENDIENTE_APROBACION")
        block = src[pend_idx:pend_idx + 30]
        assert "2" in block, "PENDIENTE_APROBACION debe mapearse al paso 2."

    def test_aprobada_maps_to_step_3(self):
        """APROBADA → step 3 (Autorizar — aprobado)."""
        src = self._src()
        aprobada_idx = src.find('"APROBADA"')
        if aprobada_idx == -1:
            aprobada_idx = src.find("'APROBADA'")
        block = src[aprobada_idx:aprobada_idx + 30]
        assert "3" in block, "APROBADA debe mapearse al paso 3."


# ── 5. _on_doc_item_clicked calls _refresh_stepper_for_doc (AST) ─────────────

class TestOnDocItemClickedWiring:
    """_on_doc_item_clicked() triggers stepper update and detail refresh."""

    def _src(self):
        return _method_src("_on_doc_item_clicked")

    def test_method_exists(self):
        assert self._src() is not None

    def test_calls_refresh_doc_detail(self):
        assert "_refresh_doc_detail" in self._src()

    def test_calls_refresh_doc_acciones(self):
        assert "_refresh_doc_acciones" in self._src()

    def test_calls_refresh_stepper_for_doc(self):
        assert "_refresh_stepper_for_doc" in self._src(), (
            "FASE 7: _on_doc_item_clicked debe llamar _refresh_stepper_for_doc() "
            "para actualizar el stepper con el estado del documento seleccionado."
        )

    def test_stores_selected_doc_estado(self):
        assert "_selected_doc_estado" in self._src(), (
            "_on_doc_item_clicked debe almacenar el estado del documento en _selected_doc_estado."
        )


# ── 6. PurchaseRequestUC state machine (integration) ─────────────────────────

class TestPurchaseRequestUCStateMachine:
    """PurchaseRequestUC enforces valid state transitions."""

    def _uc(self):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        conn = _make_pr_db()
        container = _make_pr_container(conn)
        return PurchaseRequestUC(container), conn

    def _create_pr(self, uc, estado="BORRADOR"):
        """Helper: create a PR directly via repo for testing transitions."""
        from repositories.purchase_request_repository import PurchaseRequestRepository
        conn = uc._container.db
        repo = PurchaseRequestRepository(conn)
        pr_id, folio = repo.create(
            proveedor_id=1, proveedor_nombre="Prov Test",
            sucursal_id=1, usuario="tester",
            items=[{"product_id": 1, "qty": 5, "unit_cost": 100.0, "nombre": "Pollo"}],
            metodo_pago="CONTADO", subtotal=500, iva_monto=0, total=500,
            estado=estado,
        )
        return pr_id, folio

    def test_aprobar_valid_transition(self):
        """PENDIENTE_APROBACION → APROBADA is valid."""
        uc, conn = self._uc()
        pr_id, folio = self._create_pr(uc, "PENDIENTE_APROBACION")
        result = uc.aprobar(pr_id, "admin")
        assert result.ok, f"Expected ok=True, got: {result.error}"
        assert result.estado == "APROBADA"

    def test_aprobar_invalid_from_borrador(self):
        """BORRADOR → APROBADA is invalid (must go via PENDIENTE_APROBACION)."""
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "BORRADOR")
        result = uc.aprobar(pr_id, "admin")
        assert not result.ok
        assert "BORRADOR" in result.error or "inválida" in result.error.lower()

    def test_rechazar_valid_transition(self):
        """PENDIENTE_APROBACION → RECHAZADA is valid."""
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "PENDIENTE_APROBACION")
        result = uc.rechazar(pr_id, "admin", "Precio muy alto")
        assert result.ok
        assert result.estado == "RECHAZADA"

    def test_rechazar_invalid_from_aprobada(self):
        """APROBADA → RECHAZADA is invalid."""
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "APROBADA")
        result = uc.rechazar(pr_id, "admin", "motivo")
        assert not result.ok

    def test_cancelar_valid_from_pending(self):
        """PENDIENTE_APROBACION → CANCELADA is valid."""
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "PENDIENTE_APROBACION")
        result = uc.cancelar(pr_id, "admin")
        assert result.ok

    def test_pr_not_found_returns_error(self):
        """Nonexistent PR ID returns ok=False with descriptive error."""
        uc, conn = self._uc()
        result = uc.aprobar(9999, "admin")
        assert not result.ok
        assert "9999" in result.error or "no encontrada" in result.error.lower()

    def test_listar_pendientes_returns_pending(self):
        """listar_pendientes() only returns PENDIENTE_APROBACION rows."""
        uc, conn = self._uc()
        self._create_pr(uc, "PENDIENTE_APROBACION")
        self._create_pr(uc, "APROBADA")
        self._create_pr(uc, "BORRADOR")
        result = uc.listar_pendientes(sucursal_id=1)
        assert len(result) == 1
        assert result[0]["estado"] == "PENDIENTE_APROBACION"

    def test_listar_aprobadas_returns_approved(self):
        uc, conn = self._uc()
        self._create_pr(uc, "APROBADA")
        self._create_pr(uc, "BORRADOR")
        result = uc.listar_aprobadas(sucursal_id=1)
        assert len(result) == 1
        assert result[0]["estado"] == "APROBADA"

    def test_enviar_aprobacion_from_borrador(self):
        """BORRADOR → PENDIENTE_APROBACION via enviar_aprobacion."""
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "BORRADOR")
        result = uc.enviar_aprobacion(pr_id, "user1")
        assert result.ok
        assert result.estado == "PENDIENTE_APROBACION"

    def test_repo_get_items_public_helper(self):
        from repositories.purchase_request_repository import PurchaseRequestRepository
        uc, conn = self._uc()
        pr_id, _ = self._create_pr(uc, "BORRADOR")
        repo = PurchaseRequestRepository(conn)
        items = repo.get_items(pr_id)
        assert len(items) == 1
        assert items[0]["producto_id"] == 1


# ── 7. PurchaseRequestUC convertir_a_po (integration) ────────────────────────

class TestConvertirAPO:
    """PurchaseRequestUC.convertir_a_po() creates PO and marks PR as CONVERTIDA."""

    def _setup(self):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        from repositories.purchase_request_repository import PurchaseRequestRepository
        conn = _make_pr_db()
        container = _make_pr_container(conn)
        uc = PurchaseRequestUC(container)
        repo = PurchaseRequestRepository(conn)
        pr_id, folio = repo.create(
            proveedor_id=1, proveedor_nombre="Prov Test",
            sucursal_id=1, usuario="tester",
            items=[{"product_id": 1, "qty": 5, "unit_cost": 100.0, "nombre": "Pollo"}],
            metodo_pago="CONTADO", subtotal=500, iva_monto=0, total=500,
            estado="APROBADA",
        )
        return uc, conn, pr_id, folio

    def test_convertir_creates_po(self):
        uc, conn, pr_id, _ = self._setup()
        result = uc.convertir_a_po(pr_id, "admin")
        assert result.ok, f"Expected ok=True, got: {result.error}"
        assert result.po_folio or result.po_id > 0

    def test_convertir_marks_pr_convertida(self):
        uc, conn, pr_id, _ = self._setup()
        uc.convertir_a_po(pr_id, "admin")
        row = conn.execute("SELECT estado FROM purchase_requests WHERE id=?", (pr_id,)).fetchone()
        assert row["estado"] == "CONVERTIDA_A_PO"

    def test_convertir_po_visible_in_ordenes(self):
        uc, conn, pr_id, _ = self._setup()
        result = uc.convertir_a_po(pr_id, "admin")
        row = conn.execute("SELECT estado FROM ordenes_compra WHERE id=?", (result.po_id,)).fetchone()
        assert row is not None
        assert row["estado"] == "ABIERTA"

    def test_convertir_requires_aprobada_state(self):
        uc, conn, pr_id, _ = self._setup()
        # Change state to PENDIENTE first
        conn.execute("UPDATE purchase_requests SET estado='PENDIENTE_APROBACION' WHERE id=?", (pr_id,))
        result = uc.convertir_a_po(pr_id, "admin")
        assert not result.ok
        assert "APROBADA" in result.error or "inválida" in result.error.lower()

    def test_double_convert_prevented(self):
        """Cannot convert same PR twice (CONVERTIDA_A_PO is terminal)."""
        uc, conn, pr_id, _ = self._setup()
        uc.convertir_a_po(pr_id, "admin")
        result2 = uc.convertir_a_po(pr_id, "admin")
        assert not result2.ok


# ── 8. No SQL in primary UI flows (AST) ──────────────────────────────────────

class TestNoPrimarySQL:
    """Primary action methods delegate to UCs — SQL only in except fallbacks."""

    @pytest.mark.parametrize("method_name", [
        "_accion_aprobar_pr",
        "_accion_rechazar_pr",
        "_accion_convertir_a_po",
        "_refresh_doc_acciones",
        "_refresh_stepper_for_doc",
        "_on_doc_item_clicked",
    ])
    def test_no_sql_in_primary_flow(self, method_name: str):
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        # Use "SELECT " (with trailing space) to avoid false positives from
        # variable names like self._selected_doc_id → "SELECTED_DOC_ID"
        has_raw_sql = "db.execute" in src or bool(re.search(r'\bSELECT\s+\w', src, re.IGNORECASE))
        assert not has_raw_sql, (
            f"No debe haber SQL directo en {method_name}. "
            f"Los accesos a DB van en el UC/repo."
        )


# ── 9. No banned colors in FASE 7 methods ────────────────────────────────────

class TestNoBannedColorsInFase7Methods:

    @pytest.mark.parametrize("method_name", [
        "_refresh_stepper_for_doc",
        "_on_doc_item_clicked",
        "_refresh_doc_acciones",
        "_refresh_doc_detail",
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
        "_refresh_stepper_for_doc",
        "_on_doc_item_clicked",
        "_refresh_doc_acciones",
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
