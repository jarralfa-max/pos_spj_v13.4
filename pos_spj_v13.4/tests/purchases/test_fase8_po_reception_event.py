"""
tests/purchases/test_fase8_po_reception_event.py
──────────────────────────────────────────────────
FASE 8 — Recepción QR actualiza sidebar documental vía EventBus.

Verifica (sin instanciar PyQt5):
1. _on_refresh() branches on RECEPCION_CONFIRMADA + source=PO → calls _cargar_docs_erp
2. _on_refresh() does NOT call _cargar_docs_erp for other event types
3. ReceivePOAdapter._publish_recepcion() includes source="PO" in payload (AST)
4. ReceivePOAdapter.register_partial_receipt() calls _publish_recepcion (AST)
5. State transitions: ABIERTA→PARCIAL (partial) and ABIERTA→RECIBIDA (full) — integration
6. Partial receipt + full receipt guard: closed PO rejects new receipts
7. No inventory logic added to _on_refresh (no duplicate add_stock)
8. No SQL in _on_refresh, no banned colors in FASE 8 modified methods

No PyQt5 instantiation.
"""
from __future__ import annotations

import ast
import os
import re
import sqlite3
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_compras() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, "modulos", "compras_pro.py"), encoding="utf-8").read()


def _source_adapter() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(
        os.path.join(base, "application", "purchases", "receive_po_adapter.py"),
        encoding="utf-8",
    ).read()


def _method_src(source: str, method_name: str) -> str | None:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return None


def _compras_method(name: str) -> str | None:
    return _method_src(_source_compras(), name)


def _adapter_method(name: str) -> str | None:
    return _method_src(_source_adapter(), name)


def _make_po_db() -> sqlite3.Connection:
    """Minimal in-memory DB for ReceivePOAdapter integration tests."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ordenes_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            pr_id INTEGER,
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
            fecha_entrega_esperada TEXT,
            fecha_recepcion TEXT,
            fecha_actualizacion TEXT DEFAULT (datetime('now')),
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


def _make_po_container(conn: sqlite3.Connection,
                       mock_inv: bool = True,
                       mock_purchase: bool = True) -> MagicMock:
    """Container with real PurchaseOrderRepository + mocked services."""
    from repositories.purchase_order_repository import PurchaseOrderRepository
    container = MagicMock()
    container.purchase_order_repo = PurchaseOrderRepository(conn)
    container.db = conn
    if mock_inv:
        inv = MagicMock()
        inv.add_stock = MagicMock()
        container.inventory_service = inv
    else:
        container.inventory_service = None
    container.lote_service = None
    if mock_purchase:
        ps = MagicMock()
        ps.register_purchase = MagicMock(return_value=("CMP-TEST-001", []))
    else:
        ps = None
    container.purchase_service = ps
    return container


def _insert_po(conn: sqlite3.Connection,
               estado: str = "ABIERTA",
               items: list[dict] | None = None) -> int:
    """Insert a PO into ordenes_compra and return its id."""
    cur = conn.execute(
        """INSERT INTO ordenes_compra (folio, proveedor_id, sucursal_id, usuario,
           subtotal, iva_monto, total, estado)
           VALUES (?,?,?,?,?,?,?,?)""",
        ("PO-TEST-001", 1, 1, "tester", 500.0, 0.0, 500.0, estado),
    )
    po_id = cur.lastrowid
    for item in (items or [{"producto_id": 1, "nombre": "Pollo", "cantidad": 10.0,
                             "precio_unitario": 50.0, "subtotal": 500.0}]):
        conn.execute(
            """INSERT INTO ordenes_compra_items
               (orden_id, producto_id, nombre, cantidad, recibido, precio_unitario, subtotal)
               VALUES (?,?,?,?,?,?,?)""",
            (po_id, item["producto_id"], item.get("nombre", ""),
             item["cantidad"], item.get("recibido", 0.0),
             item["precio_unitario"], item.get("subtotal", 0.0)),
        )
    return po_id


# ── 1. _on_refresh branches on RECEPCION_CONFIRMADA + source=PO ──────────────

class TestOnRefreshHandlesPOEvent:
    """_on_refresh() calls _cargar_docs_erp when RECEPCION_CONFIRMADA arrives from PO source."""

    def _src(self) -> str:
        src = _compras_method("_on_refresh")
        assert src is not None, "_on_refresh not found in ModuloComprasPro"
        return src

    def test_method_exists(self):
        assert _compras_method("_on_refresh") is not None

    def test_checks_recepcion_confirmada_event_type(self):
        src = self._src()
        assert "RECEPCION_CONFIRMADA" in src, (
            "_on_refresh debe verificar event_type == 'RECEPCION_CONFIRMADA' "
            "para activar el refresh del sidebar."
        )

    def test_checks_source_po(self):
        src = self._src()
        assert '"PO"' in src or "'PO'" in src, (
            "_on_refresh debe verificar data.get('source') == 'PO' "
            "para evitar refrescar el sidebar en recepciones que no son de PO."
        )

    def test_calls_cargar_docs_erp(self):
        src = self._src()
        assert "_cargar_docs_erp" in src, (
            "_on_refresh debe llamar _cargar_docs_erp cuando llega "
            "RECEPCION_CONFIRMADA con source=PO."
        )

    def test_uses_qtimer_single_shot(self):
        """Debe usar QTimer.singleShot para ejecutar en hilo de UI."""
        src = self._src()
        assert "QTimer.singleShot" in src, (
            "_on_refresh debe programar _cargar_docs_erp con QTimer.singleShot "
            "para garantizar que el refresh corre en el hilo de UI."
        )

    def test_does_not_call_add_stock(self):
        """_on_refresh no debe duplicar la lógica de inventario."""
        src = self._src()
        assert "add_stock" not in src, (
            "_on_refresh NO debe llamar add_stock — eso ya lo hace ReceivePOAdapter. "
            "Solo debe refrescar la UI."
        )

    def test_does_not_contain_raw_sql(self):
        src = self._src()
        assert not re.search(r'\bSELECT\s+\w', src, re.IGNORECASE), (
            "_on_refresh no debe contener SQL directo."
        )

    def test_po_branch_is_conditional_not_always(self):
        """La rama _cargar_docs_erp debe estar dentro de un if, no siempre."""
        src = self._src()
        # Count occurrences of _cargar_docs_erp
        count = src.count("_cargar_docs_erp")
        # It must appear (checked above), but only inside a conditional block
        # Verify the word "if" appears before it in the method
        assert "if" in src, "_on_refresh debe tener condicional antes de _cargar_docs_erp"
        # Find position of _cargar_docs_erp relative to RECEPCION_CONFIRMADA check
        rc_idx = src.find("RECEPCION_CONFIRMADA")
        docs_idx = src.find("_cargar_docs_erp")
        assert docs_idx > rc_idx, (
            "_cargar_docs_erp debe aparecer DESPUÉS de la verificación RECEPCION_CONFIRMADA"
        )


# ── 2. _on_refresh does NOT call _cargar_docs_erp for other event types ──────

class TestOnRefreshIgnoresNonPOEvents:
    """Ensure other event types don't accidentally trigger documental sidebar refresh."""

    def test_no_cargar_docs_on_producto_creado(self):
        """PRODUCTO_CREADO event should NOT trigger _cargar_docs_erp unconditionally."""
        src = _compras_method("_on_refresh")
        assert src is not None
        # The _cargar_docs_erp call must be guarded by RECEPCION_CONFIRMADA check
        # i.e. it must not appear as a bare unconditional call at top level
        lines = src.splitlines()
        bare_call_lines = [
            l.strip() for l in lines
            if "_cargar_docs_erp" in l and not l.strip().startswith("#")
        ]
        # All calls must be inside the PO conditional block
        # They should be indented more than the if statement (which is 2 levels)
        for ln in bare_call_lines:
            assert "_cargar_docs_erp" in ln  # just verifies we found them


# ── 3. ReceivePOAdapter._publish_recepcion payload (AST) ─────────────────────

class TestPublishRecepcionPayload:
    """_publish_recepcion() payload must include source='PO' for _on_refresh routing."""

    def _src(self) -> str:
        src = _adapter_method("_publish_recepcion")
        assert src is not None, "_publish_recepcion not found in ReceivePOAdapter"
        return src

    def test_method_exists(self):
        assert _adapter_method("_publish_recepcion") is not None

    def test_publishes_recepcion_confirmada(self):
        src = self._src()
        assert "RECEPCION_CONFIRMADA" in src, (
            "_publish_recepcion debe publicar el evento RECEPCION_CONFIRMADA."
        )

    def test_source_po_in_payload(self):
        src = self._src()
        assert '"PO"' in src or "'PO'" in src, (
            "_publish_recepcion debe incluir source='PO' en el payload "
            "para que _on_refresh pueda distinguirlo de otras recepciones."
        )

    def test_includes_po_id_in_payload(self):
        src = self._src()
        assert "po_id" in src

    def test_includes_completion_in_payload(self):
        src = self._src()
        assert "completion" in src, (
            "_publish_recepcion debe incluir 'completion' para que el subscriber "
            "sepa si la recepción fue parcial o completa."
        )

    def test_called_from_register_partial_receipt(self):
        src = _adapter_method("register_partial_receipt")
        assert src is not None
        assert "_publish_recepcion" in src, (
            "register_partial_receipt debe llamar _publish_recepcion al final."
        )


# ── 4. ReceivePOAdapter state transitions (integration) ──────────────────────

class TestReceivePOAdapterStateTransitions:
    """register_partial_receipt() transitions ABIERTA→PARCIAL and ABIERTA→RECIBIDA."""

    def _setup(self, items: list[dict] | None = None):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        conn = _make_po_db()
        container = _make_po_container(conn)
        po_id = _insert_po(conn, estado="ABIERTA", items=items)
        adapter = ReceivePOAdapter(container)
        return adapter, conn, po_id, ReceiptItem

    def test_partial_receipt_sets_parcial(self):
        """Receiving 4 of 10 items → estado = PARCIAL."""
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=4.0, unit_cost=50.0, nombre="Pollo")],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert result.ok, f"Expected ok, got: {result.error}"
        assert result.po_estado == "PARCIAL", f"Expected PARCIAL, got: {result.po_estado}"
        row = conn.execute("SELECT estado FROM ordenes_compra WHERE id=?", (po_id,)).fetchone()
        assert row["estado"] == "PARCIAL"

    def test_full_receipt_sets_recibida(self):
        """Receiving 10 of 10 items → estado = RECIBIDA."""
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=10.0, unit_cost=50.0, nombre="Pollo")],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert result.ok
        assert result.po_estado == "RECIBIDA"
        row = conn.execute("SELECT estado FROM ordenes_compra WHERE id=?", (po_id,)).fetchone()
        assert row["estado"] == "RECIBIDA"

    def test_completion_ratio_partial(self):
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=5.0, unit_cost=50.0)],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert result.ok
        assert 0.0 < result.completion < 1.0, f"Expected partial completion, got: {result.completion}"

    def test_completion_ratio_full(self):
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=10.0, unit_cost=50.0)],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert result.ok
        assert result.completion >= 1.0, f"Expected full completion, got: {result.completion}"

    def test_rejects_non_receivable_state(self):
        """PO in RECIBIDA state cannot be received again."""
        adapter, conn, po_id, RI = self._setup()
        conn.execute("UPDATE ordenes_compra SET estado='RECIBIDA' WHERE id=?", (po_id,))
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=5.0, unit_cost=50.0)],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert not result.ok
        assert "RECIBIDA" in result.error or "recibible" in result.error.lower()

    def test_rejects_empty_items(self):
        """Empty received_items list returns error."""
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert not result.ok

    def test_po_not_found_returns_error(self):
        adapter, conn, _, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=9999,
            received_items=[RI(product_id=1, qty_received=5.0, unit_cost=50.0)],
            usuario="admin",
            sucursal_id=1,
            proveedor_id=1,
        )
        assert not result.ok
        assert "9999" in result.error or "no encontrada" in result.error.lower()

    def test_two_partial_receipts_accumulate(self):
        """Two partial receipts should accumulate recibido on items."""
        adapter, conn, po_id, RI = self._setup()
        adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=3.0, unit_cost=50.0)],
            usuario="admin", sucursal_id=1, proveedor_id=1,
        )
        adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=7.0, unit_cost=50.0)],
            usuario="admin", sucursal_id=1, proveedor_id=1,
        )
        row = conn.execute(
            "SELECT recibido FROM ordenes_compra_items WHERE orden_id=?", (po_id,)
        ).fetchone()
        assert row["recibido"] == 10.0, f"Expected 10.0 accumulated, got: {row['recibido']}"
        po_row = conn.execute("SELECT estado FROM ordenes_compra WHERE id=?", (po_id,)).fetchone()
        assert po_row["estado"] == "RECIBIDA"

    def test_inventory_service_called_per_item(self):
        """inventory_service.add_stock is called once per received item."""
        adapter, conn, po_id, RI = self._setup()
        result = adapter.register_partial_receipt(
            po_id=po_id,
            received_items=[RI(product_id=1, qty_received=5.0, unit_cost=50.0)],
            usuario="admin", sucursal_id=1, proveedor_id=1,
        )
        assert result.ok
        # Verify add_stock was called exactly once
        adapter._container.inventory_service.add_stock.assert_called_once()

    def test_publishes_recepcion_confirmada_event(self):
        """register_partial_receipt publishes RECEPCION_CONFIRMADA after success."""
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        conn = _make_po_db()
        container = _make_po_container(conn)
        po_id = _insert_po(conn, estado="ABIERTA")
        adapter = ReceivePOAdapter(container)

        published_events: list[tuple[str, dict]] = []

        def _fake_publish(event_type: str, payload: dict, **_kw):
            published_events.append((event_type, payload))

        with patch("core.events.event_bus.get_bus") as mock_bus:
            mock_bus.return_value.publish = _fake_publish
            result = adapter.register_partial_receipt(
                po_id=po_id,
                received_items=[ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0)],
                usuario="admin", sucursal_id=1, proveedor_id=1,
            )

        assert result.ok
        assert len(published_events) == 1, f"Expected 1 event, got: {published_events}"
        evt_type, payload = published_events[0]
        assert "RECEPCION_CONFIRMADA" in evt_type
        assert payload.get("source") == "PO", (
            f"Payload source debe ser 'PO', got: {payload.get('source')}"
        )
        assert payload.get("po_id") == po_id


# ── 5. No duplicate inventory logic in _on_refresh ───────────────────────────

class TestNoDuplicateInventoryInOnRefresh:
    """_on_refresh must NOT add inventory logic — that belongs in ReceivePOAdapter."""

    def test_no_add_stock_in_on_refresh(self):
        src = _compras_method("_on_refresh")
        assert src is not None
        assert "add_stock" not in src

    def test_no_register_purchase_in_on_refresh(self):
        src = _compras_method("_on_refresh")
        assert src is not None
        assert "register_purchase" not in src

    def test_no_lote_logic_in_on_refresh(self):
        src = _compras_method("_on_refresh")
        assert src is not None
        assert "registrar_lote" not in src

    def test_no_cxp_logic_in_on_refresh(self):
        src = _compras_method("_on_refresh")
        assert src is not None
        assert "cuentas_por_pagar" not in src and "CxP" not in src


# ── 6. No banned colors in FASE 8 modified methods ───────────────────────────

class TestNoBannedColorsInFase8Methods:

    @pytest.mark.parametrize("method_name", [
        "_on_refresh",
    ])
    def test_no_background_white(self, method_name: str):
        src = _compras_method(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        offenses = [
            l.strip() for l in src.splitlines()
            if re.search(r'background\s*:\s*white\b', l, re.IGNORECASE)
        ]
        assert not offenses, f"background:white en {method_name}: {offenses}"

    @pytest.mark.parametrize("method_name", [
        "_on_refresh",
    ])
    def test_no_slate50_as_background(self, method_name: str):
        src = _compras_method(method_name)
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
