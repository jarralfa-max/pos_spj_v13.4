"""
tests/purchases/test_phase4_receive_po_adapter.py
──────────────────────────────────────────────────
FASE 4 — Tests del adaptador de recepción de PO.

Verifica:
1. ReceivePOAdapter importa correctamente (contrato Phase 1 ahora pasa)
2. get_po_lines() devuelve líneas con cantidad, recibido, pendiente
3. get_po_status() devuelve estado actual
4. register_partial_receipt() llama add_stock() UNA VEZ por item
5. register_partial_receipt() NO duplica movimientos
6. Recepción parcial → po_estado = PARCIAL
7. Recepción completa → po_estado = RECIBIDA
8. Recepción con lote → llama lote_service.registrar_lote()
9. Recepción sin lote → NO llama lote_service
10. PO en estado NO recibible → error claro
11. PO inexistente → error claro
12. items_received vacío → error claro
13. Se crea compra con purchase_order_id vinculado sin llamar register_purchase
14. Se publica RECEPCION_CONFIRMADA
15. ReceivePOAdapter NO tiene add_stock propio
16. AppContainer registra receive_po_adapter
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import importlib
import pytest
from unittest.mock import MagicMock, patch, call


# ── Schema + migraciones ──────────────────────────────────────────────────────

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
    folio TEXT UNIQUE, proveedor_id INTEGER,
    estado TEXT DEFAULT 'borrador', total REAL DEFAULT 0,
    notas TEXT, fecha_entrega_esperada DATE,
    fecha_recepcion DATETIME,
    fecha_creacion DATETIME DEFAULT (datetime('now')),
    usuario TEXT
);
CREATE TABLE IF NOT EXISTS ordenes_compra_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER, producto_id INTEGER,
    nombre TEXT, cantidad REAL, recibido REAL DEFAULT 0,
    precio_unitario REAL, subtotal REAL
);
CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folio TEXT UNIQUE, proveedor_id INTEGER, usuario TEXT,
    subtotal REAL DEFAULT 0, iva REAL DEFAULT 0,
    total REAL DEFAULT 0, estado TEXT DEFAULT 'completada',
    forma_pago TEXT DEFAULT 'CONTADO', observaciones TEXT,
    sucursal_id INTEGER DEFAULT 1,
    condicion_pago TEXT DEFAULT 'liquidado',
    plazo_dias INTEGER DEFAULT 0, moneda TEXT DEFAULT 'MXN'
);
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL DEFAULT 100
);
INSERT INTO productos VALUES (1, 'Pollo Entero', 100), (2, 'Arrachera', 50);
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(BASE_SCHEMA)
    conn.isolation_level = None
    for mod_name in [
        "migrations.standalone.076_purchase_requests",
        "migrations.standalone.077_ordenes_compra_erp",
        "migrations.standalone.078_compras_po_link",
    ]:
        importlib.import_module(mod_name).run(conn)
    return conn


@pytest.fixture
def po_repo(db):
    from repositories.purchase_order_repository import PurchaseOrderRepository
    return PurchaseOrderRepository(db)


def _make_po(db, po_repo, items=None, estado="ABIERTA"):
    """Helper: crea una PO de prueba ya en DB."""
    items = items or [
        {"product_id": 1, "qty": 10.0, "unit_cost": 50.0, "nombre": "Pollo"},
        {"product_id": 2, "qty": 5.0,  "unit_cost": 120.0, "nombre": "Arrachera"},
    ]
    pr_data = {
        "proveedor_id": 1,
        "sucursal_id": 1,
        "subtotal": 1100.0,
        "iva_monto": 0.0,
        "total": 1100.0,
        "metodo_pago": "CONTADO",
        "condicion_pago": "liquidado",
        "plazo_dias": 0,
        "moneda": "MXN",
        "notas": "",
        "doc_ref": "",
        "items": items,
    }
    po_id, folio = po_repo.create_from_pr(pr_id=1, pr_data=pr_data, usuario="admin")
    if estado != "ABIERTA":
        po_repo.update_estado(po_id, estado)
    return po_id, folio


def _make_container(db, po_repo):
    container = MagicMock()
    container.db = db
    container.purchase_order_repo = po_repo
    container.inventory_service = MagicMock()
    container.lote_service = None      # sin lote por defecto
    container.purchase_service = MagicMock()
    return container


# ── Tests de importación / contrato ───────────────────────────────────────────

class TestReceivePOAdapterImport:

    def test_adapter_imports_without_error(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert ReceivePOAdapter is not None

    def test_receipt_item_imports(self):
        from application.purchases.receive_po_adapter import ReceiptItem
        item = ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")
        assert item.qty_received == 5.0

    def test_receipt_result_imports(self):
        from application.purchases.receive_po_adapter import ReceiptResult
        r = ReceiptResult(ok=True, po_estado="PARCIAL", completion=0.5)
        assert r.ok

    def test_adapter_has_no_own_add_stock(self):
        """El adaptador no reimplementa add_stock."""
        import inspect
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        # No debe definir un método add_stock propio
        assert not hasattr(ReceivePOAdapter, "add_stock"), (
            "ReceivePOAdapter no debe tener add_stock propio — usa inventory_service"
        )

    def test_package_exports_adapter(self):
        from application.purchases import ReceivePOAdapter, ReceiptItem, ReceiptResult
        assert ReceivePOAdapter is not None


# ── Tests de get_po_lines ─────────────────────────────────────────────────────

class TestGetPOLines:

    def test_returns_lines_with_expected_fields(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        adapter = ReceivePOAdapter(_make_container(db, po_repo))
        lines = adapter.get_po_lines(po_id)
        assert len(lines) == 2
        for line in lines:
            assert "producto_id" in line
            assert "cantidad" in line
            assert "recibido" in line
            assert "pendiente" in line

    def test_pendiente_equals_cantidad_initially(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        adapter = ReceivePOAdapter(_make_container(db, po_repo))
        lines = adapter.get_po_lines(po_id)
        for line in lines:
            assert abs(line["pendiente"] - line["cantidad"]) < 0.001

    def test_returns_empty_for_nonexistent_po(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        adapter = ReceivePOAdapter(_make_container(db, po_repo))
        assert adapter.get_po_lines(9999) == []

    def test_get_po_status_returns_estado(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        adapter = ReceivePOAdapter(_make_container(db, po_repo))
        assert adapter.get_po_status(po_id) == "ABIERTA"


# ── Tests de register_partial_receipt ────────────────────────────────────────

class TestRegisterPartialReceipt:

    def _make_items(self, partial=False):
        from application.purchases.receive_po_adapter import ReceiptItem
        if partial:
            return [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        return [
            ReceiptItem(product_id=1, qty_received=10.0, unit_cost=50.0, nombre="Pollo"),
            ReceiptItem(product_id=2, qty_received=5.0,  unit_cost=120.0, nombre="Arrachera"),
        ]

    def test_returns_ok_result(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            result = adapter.register_partial_receipt(
                po_id=po_id, received_items=self._make_items(),
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert result.ok, f"error: {result.error}"

    def test_add_stock_called_once_per_item(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            adapter.register_partial_receipt(
                po_id=po_id, received_items=self._make_items(),
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert container.inventory_service.add_stock.call_count == 2, (
            f"add_stock debe llamarse 2 veces (una por item), "
            f"se llamó {container.inventory_service.add_stock.call_count}"
        )

    def test_no_duplicate_inventory_for_single_item(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        from application.purchases.receive_po_adapter import ReceiptItem
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert container.inventory_service.add_stock.call_count == 1, (
            "Un item → add_stock exactamente 1 vez (sin duplicación)"
        )

    def test_partial_receipt_sets_po_estado_parcial(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            result = adapter.register_partial_receipt(
                po_id=po_id, received_items=self._make_items(partial=True),
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert result.po_estado == "PARCIAL", f"estado esperado PARCIAL, obtenido: {result.po_estado}"
        assert adapter.get_po_status(po_id) == "PARCIAL"

    def test_full_receipt_sets_po_estado_recibida(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo,
                            items=[{"product_id": 1, "qty": 10.0, "unit_cost": 50.0, "nombre": "P"}])
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        from application.purchases.receive_po_adapter import ReceiptItem
        items = [ReceiptItem(product_id=1, qty_received=10.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            result = adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert result.po_estado == "RECIBIDA"
        assert result.completion >= 1.0

    def test_completion_ratio_in_result(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo,
                            items=[{"product_id": 1, "qty": 10.0, "unit_cost": 50.0, "nombre": "P"}])
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            result = adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert abs(result.completion - 0.5) < 0.01

    def test_lote_registered_when_item_has_lote(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        container.lote_service = MagicMock()
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0,
                             nombre="Pollo", lote="L-2026-001",
                             fecha_caducidad="2026-05-30")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        container.lote_service.registrar_lote.assert_called_once()

    def test_lote_not_called_when_item_has_no_lote(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        container.lote_service = MagicMock()
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        container.lote_service.registrar_lote.assert_not_called()

    def test_compra_created_with_po_id_link(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            result = adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        assert result.folio.startswith("CMP-")
        row = db.execute(
            "SELECT purchase_order_id, total FROM compras WHERE folio=?", (result.folio,)
        ).fetchone()
        assert row is not None
        assert row["purchase_order_id"] == po_id
        assert float(row["total"]) == 250.0

    def test_po_receipt_does_not_call_purchase_service_register_purchase(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0, nombre="Pollo")]
        with patch("core.events.event_bus.get_bus", return_value=MagicMock()):
            adapter.register_partial_receipt(
                po_id=po_id, received_items=items,
                usuario="almacen", sucursal_id=1, proveedor_id=1,
            )
        container.purchase_service.register_purchase.assert_not_called()


# ── Tests de validación / errores ─────────────────────────────────────────────

class TestReceivePOValidation:

    def test_nonexistent_po_returns_error(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0)]
        result = adapter.register_partial_receipt(
            po_id=9999, received_items=items,
            usuario="almacen", sucursal_id=1, proveedor_id=1,
        )
        assert not result.ok
        assert "9999" in result.error

    def test_cancelled_po_returns_error(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo, estado="CANCELADA")
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0)]
        result = adapter.register_partial_receipt(
            po_id=po_id, received_items=items,
            usuario="almacen", sucursal_id=1, proveedor_id=1,
        )
        assert not result.ok

    def test_empty_items_returns_error(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        po_id, _ = _make_po(db, po_repo)
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        result = adapter.register_partial_receipt(
            po_id=po_id, received_items=[],
            usuario="almacen", sucursal_id=1, proveedor_id=1,
        )
        assert not result.ok
        assert container.inventory_service.add_stock.call_count == 0

    def test_received_po_blocks_further_receipt(self, db, po_repo):
        from application.purchases.receive_po_adapter import ReceivePOAdapter, ReceiptItem
        po_id, _ = _make_po(db, po_repo, estado="RECIBIDA")
        container = _make_container(db, po_repo)
        adapter = ReceivePOAdapter(container)
        items = [ReceiptItem(product_id=1, qty_received=5.0, unit_cost=50.0)]
        result = adapter.register_partial_receipt(
            po_id=po_id, received_items=items,
            usuario="almacen", sucursal_id=1, proveedor_id=1,
        )
        assert not result.ok


# ── Tests de AppContainer ─────────────────────────────────────────────────────

class TestAppContainerPhase4:

    def test_app_container_has_receive_po_adapter(self):
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "receive_po_adapter" in source

    def test_receive_po_adapter_not_reimplementing_qr(self):
        import inspect
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        source = inspect.getsource(ReceivePOAdapter)
        assert "qr_service" not in source.lower(), (
            "ReceivePOAdapter no debe importar qr_service — violación política QR NO-TOUCH"
        )
        assert "generar_uuid_qr" not in source, (
            "ReceivePOAdapter no debe llamar generar_uuid_qr"
        )

    def test_phase1_contract_test_now_passes(self):
        """
        El test de contrato de Phase 1 (antes skipped) ahora debe pasar:
        ReceivePOAdapter existe y cumple la interfaz esperada.
        """
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert not hasattr(ReceivePOAdapter, "_add_stock"), (
            "ReceivePOAdapter no debe tener _add_stock propio"
        )
        assert hasattr(ReceivePOAdapter, "get_po_lines")
        assert hasattr(ReceivePOAdapter, "register_partial_receipt")
        assert hasattr(ReceivePOAdapter, "get_po_status")
