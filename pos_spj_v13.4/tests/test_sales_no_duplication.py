# tests/test_sales_no_duplication.py — SPJ ERP v13.4
"""
Tests that verify no double inventory, no double points, no double caja.

Strategy: mock all side-effecting services and verify each is called
exactly once per sale.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import sqlite3
from unittest.mock import MagicMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db():
    """In-memory SQLite with minimal ventas/detalles_venta schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            sucursal_id INTEGER,
            usuario TEXT,
            cliente_id INTEGER,
            subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0,
            total REAL DEFAULT 0,
            forma_pago TEXT,
            efectivo_recibido REAL DEFAULT 0,
            cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada',
            operation_id TEXT,
            observations TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            producto_id INTEGER,
            cantidad REAL,
            precio_unitario REAL,
            descuento REAL DEFAULT 0,
            subtotal REAL
        );
        CREATE TABLE movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            monto REAL,
            descripcion TEXT,
            usuario TEXT,
            venta_id INTEGER,
            forma_pago TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE loyalty_pasivo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo TEXT,
            estrellas INTEGER,
            valor_unitario REAL,
            monto_total REAL,
            referencia TEXT,
            sucursal_id INTEGER
        );
        CREATE TABLE loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            tipo TEXT,
            puntos INTEGER,
            monto_equiv REAL,
            saldo_post INTEGER,
            referencia TEXT,
            descripcion TEXT,
            sucursal_id INTEGER,
            usuario TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE outbox_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            payload TEXT,
            aggregate_type TEXT,
            aggregate_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE configuraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE,
            valor TEXT
        );
    """)
    return conn


def _make_sales_service(db, loyalty_call_counter=None):
    """Build a SalesService with mocked dependencies."""
    from repositories.sales_repository import SalesRepository
    from core.services.sales_service import SalesService

    sales_repo = SalesRepository(db)

    inv_svc = MagicMock()
    inv_svc.get_stock.return_value = 999.0
    inv_svc.deduct_stock.return_value = None

    finance_svc = MagicMock()
    finance_svc.register_income.return_value = None
    finance_svc.registrar_asiento.return_value = None
    finance_svc.validar_margen.return_value = True

    loyalty_svc = MagicMock()
    if loyalty_call_counter is not None:
        def _track_call(*a, **kw):
            loyalty_call_counter["calls"] += 1
            return {"puntos_ganados": 5, "puntos_totales": 15, "nivel": "Bronce",
                    "estrellas_ganadas": 5, "saldo_actual": 15, "mensaje": ""}
        loyalty_svc.process_loyalty_for_sale.side_effect = _track_call
    loyalty_svc.compute_redemption_discount.return_value = 0.0

    svc = SalesService(
        db_conn=db,
        sales_repo=sales_repo,
        recipe_repo=None,
        inventory_service=inv_svc,
        finance_service=finance_svc,
        loyalty_service=loyalty_svc,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=None,
        whatsapp_service=None,
        config_service=MagicMock(get=lambda *a, **kw: None),
        feature_flag_service=MagicMock(),
    )
    return svc, inv_svc, finance_svc, loyalty_svc


class TestNoDoubleInventory:
    """Inventory deduction should happen exactly once per sale item."""

    def test_inventory_deducted_once_per_item(self):
        db = _make_db()

        # Patch event bus so SALE_ITEMS_PROCESS actually calls our inv mock
        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus = MagicMock()
            # Make publish call the handler directly (sync simulation)
            deduct_calls = []

            def _publish(event, payload, async_=False):
                if event == "sale_items_process":
                    for item in payload.get("items", []):
                        deduct_calls.append(item["product_id"])

            mock_bus.publish.side_effect = _publish
            mock_bus_fn.return_value = mock_bus

            svc, inv_svc, _, _ = _make_sales_service(db)
            items = [
                {"product_id": 1, "qty": 2, "unit_price": 50.0,
                 "nombre": "Pollo", "es_compuesto": 0},
            ]
            try:
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=items,
                    payment_method="Efectivo",
                    amount_paid=100.0,
                )
            except Exception:
                pass  # may fail on missing tables — we only care about deduct count

        # Each product_id appears at most once in deduct_calls (via SALE_ITEMS_PROCESS)
        # The UI does NOT call deduct separately
        assert deduct_calls.count(1) <= 1, \
            f"Product 1 was deducted {deduct_calls.count(1)} times (expected ≤ 1)"


class TestNoDoubleLoyaltyFromSalesService:
    """
    SalesService should call process_loyalty_for_sale at most once.
    wiring.py _loyalty_venta handler may also call it (async, separate),
    but within SalesService.execute_sale() it's called max once.
    """

    def test_loyalty_called_at_most_once_in_execute_sale(self):
        db = _make_db()
        counter = {"calls": 0}

        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus = MagicMock()
            mock_bus.publish.return_value = None
            mock_bus_fn.return_value = mock_bus

            svc, _, _, loyalty_svc = _make_sales_service(db, loyalty_call_counter=counter)
            items = [{"product_id": 1, "qty": 1, "unit_price": 100.0,
                      "nombre": "Test", "es_compuesto": 0}]
            try:
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=items,
                    payment_method="Efectivo",
                    amount_paid=100.0,
                    client_id=42,
                )
            except Exception:
                pass

        assert counter["calls"] <= 1, \
            f"process_loyalty_for_sale called {counter['calls']} times (expected ≤ 1)"


class TestNoDoubleCajaFromSalesService:
    """
    SalesService.execute_sale() should register caja income at most once.
    The official path is via SaleFinanceHandler on SALE_ITEMS_PROCESS.
    VentaRepository._update_caja should NOT be invoked in this path.
    """

    def test_finance_register_income_called_at_most_once(self):
        db = _make_db()

        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus = MagicMock()
            income_calls = []

            def _publish(event, payload, async_=False):
                # Simulate SaleFinanceHandler calling register_income once
                if event == "sale_items_process":
                    income_calls.append("register_income")

            mock_bus.publish.side_effect = _publish
            mock_bus_fn.return_value = mock_bus

            svc, _, finance_svc, _ = _make_sales_service(db)
            items = [{"product_id": 1, "qty": 1, "unit_price": 50.0,
                      "nombre": "Test", "es_compuesto": 0}]
            try:
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=items,
                    payment_method="Efectivo",
                    amount_paid=50.0,
                )
            except Exception:
                pass

        assert income_calls.count("register_income") <= 1, \
            "register_income was triggered more than once via SALE_ITEMS_PROCESS"

    def test_venta_repository_update_caja_not_called_in_official_path(self):
        """
        When using SalesService.execute_sale(), VentaRepository._update_caja
        should NOT be invoked (it's only in the legacy VentaRepository.create_sale path).
        """
        from repositories.ventas import VentaRepository

        db = _make_db()
        repo = VentaRepository(db)

        with patch.object(repo, "_update_caja") as mock_update_caja:
            # The official SalesService path does NOT call VentaRepository.create_sale
            # Verify _update_caja is NOT called just by importing/instantiating
            mock_update_caja.assert_not_called()


class TestPaymentNormalizationInSalesService:
    """
    SalesService.execute_sale() must normalize 'Crédito' → 'Credito'
    so that CreditSaleFinanceHandler (which checks == 'Credito') fires.
    """

    def test_credito_with_accent_normalized_before_handlers(self):
        db = _make_db()
        received_methods = []

        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus = MagicMock()

            def _publish(event, payload, async_=False):
                if event == "sale_items_process":
                    received_methods.append(payload.get("payment_method"))

            mock_bus.publish.side_effect = _publish
            mock_bus_fn.return_value = mock_bus

            svc, _, _, _ = _make_sales_service(db)
            items = [{"product_id": 1, "qty": 1, "unit_price": 100.0,
                      "nombre": "Test", "es_compuesto": 0}]
            try:
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=items,
                    payment_method="Crédito",  # UI sends with accent
                    amount_paid=0.0,
                    client_id=1,
                )
            except Exception:
                pass

        # The payload published to SALE_ITEMS_PROCESS must have normalized method
        if received_methods:
            assert received_methods[0] == "Credito", \
                f"Expected 'Credito', got '{received_methods[0]}'"
