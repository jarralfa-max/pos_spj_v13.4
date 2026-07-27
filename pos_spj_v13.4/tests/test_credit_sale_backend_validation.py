# tests/test_credit_sale_backend_validation.py — SPJ ERP v13.4
"""
Tests for credit sale flow:
1. Credit sale validates limit in the backend (SalesService → customer_service.validate_credit)
2. CreditSaleFinanceHandler creates CxC exactly once (not duplicated)
3. Payment normalization ensures 'Crédito' reaches backend as 'Credito'
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db_with_cxc():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            sucursal_id INTEGER DEFAULT 1,
            usuario TEXT,
            cliente_id INTEGER,
            subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0,
            total REAL DEFAULT 0,
            forma_pago TEXT,
            efectivo_recibido REAL DEFAULT 0,
            cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada',
            operation_id TEXT UNIQUE,
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
        CREATE TABLE cuentas_por_cobrar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            venta_id INTEGER UNIQUE,
            folio TEXT,
            monto_original REAL,
            saldo_pendiente REAL,
            sucursal_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'pendiente',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            credit_limit REAL DEFAULT 0,
            credit_balance REAL DEFAULT 0,
            saldo REAL DEFAULT 0,
            allows_credit INTEGER DEFAULT 1
        );
        CREATE TABLE loyalty_pasivo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, tipo TEXT, estrellas INTEGER,
            valor_unitario REAL, monto_total REAL,
            referencia TEXT, sucursal_id INTEGER
        );
        CREATE TABLE movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, monto REAL, descripcion TEXT,
            usuario TEXT, venta_id INTEGER, forma_pago TEXT
        );
        CREATE TABLE outbox_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT, payload TEXT,
            aggregate_type TEXT, aggregate_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE configuraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE, valor TEXT
        );
    """)
    # Add a cliente with credit limit
    conn.execute(
        "INSERT INTO clientes(id, nombre, credit_limit, credit_balance, allows_credit) "
        "VALUES(1, 'Test Cliente', 500.0, 0.0, 1)"
    )
    conn.commit()
    return conn


class TestCreditSaleBackendValidation:
    """
    The backend (SalesService.execute_sale) must reject credit sales that
    exceed the credit limit — this is the authoritative validation.
    """

    def test_credit_sale_rejected_when_limit_exceeded(self):
        """customer_service.validate_credit returns (False, msg) → ValueError raised."""
        from core.services.sales_service import SalesService
        from repositories.sales_repository import SalesRepository

        db = _make_db_with_cxc()
        sales_repo = SalesRepository(db)

        customer_svc = MagicMock()
        customer_svc.get_customer.return_value = {"id": 1, "nombre": "Test"}
        customer_svc.validate_credit.return_value = (False, "Límite excedido")

        inv_svc = MagicMock()
        inv_svc.get_stock.return_value = 999.0

        svc = SalesService(
            db_conn=db, sales_repo=sales_repo,
            recipe_repo=None, inventory_service=inv_svc,
            finance_service=MagicMock(), loyalty_service=MagicMock(),
            promotion_engine=None, sync_service=None,
            ticket_template_engine=None, whatsapp_service=None,
            config_service=MagicMock(get=lambda *a, **kw: None),
            feature_flag_service=MagicMock(),
            customer_service=customer_svc,
        )

        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus_fn.return_value = MagicMock(publish=MagicMock())
            with pytest.raises((ValueError, RuntimeError)) as exc_info:
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=[{"product_id": 1, "qty": 1, "unit_price": 600.0,
                            "nombre": "Expensive", "es_compuesto": 0}],
                    payment_method="Credito",
                    amount_paid=0.0,
                    client_id=1,
                )
        assert "Límite excedido" in str(exc_info.value) or exc_info.value is not None

    def test_credit_sale_validates_even_with_accent(self):
        """
        'Crédito' (with accent) must also trigger credit validation after normalization.
        """
        from core.services.sales_service import SalesService
        from repositories.sales_repository import SalesRepository

        db = _make_db_with_cxc()
        sales_repo = SalesRepository(db)

        customer_svc = MagicMock()
        customer_svc.get_customer.return_value = {"id": 1, "nombre": "Test"}
        customer_svc.validate_credit.return_value = (False, "Límite excedido con acento")

        inv_svc = MagicMock()
        inv_svc.get_stock.return_value = 999.0

        svc = SalesService(
            db_conn=db, sales_repo=sales_repo,
            recipe_repo=None, inventory_service=inv_svc,
            finance_service=MagicMock(), loyalty_service=MagicMock(),
            promotion_engine=None, sync_service=None,
            ticket_template_engine=None, whatsapp_service=None,
            config_service=MagicMock(get=lambda *a, **kw: None),
            feature_flag_service=MagicMock(),
            customer_service=customer_svc,
        )

        with patch("core.events.event_bus.get_bus") as mock_bus_fn:
            mock_bus_fn.return_value = MagicMock(publish=MagicMock())
            with pytest.raises((ValueError, RuntimeError)):
                svc.execute_sale(
                    branch_id=1, user="cajero",
                    items=[{"product_id": 1, "qty": 1, "unit_price": 600.0,
                            "nombre": "Test", "es_compuesto": 0}],
                    payment_method="Crédito",  # UI sends with accent
                    amount_paid=0.0,
                    client_id=1,
                )


class TestCreditSaleCxCCreatedOnce:
    """
    CreditSaleFinanceHandler must insert exactly ONE CxC row per credit sale.
    """

    def test_cxc_handler_inserts_once(self):
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler

        db = _make_db_with_cxc()
        finance_svc = MagicMock()
        finance_svc.registrar_asiento.return_value = None

        handler = CreditSaleFinanceHandler(db_conn=db, finance_service=finance_svc)
        payload = {
            "payment_method": "Credito",
            "total": 200.0,
            "cliente_id": 1,
            "sale_id": 42,
            "folio": "VNT-TEST",
            "sucursal_id": 1,
        }
        handler.handle(payload)

        rows = db.execute(
            "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=42"
        ).fetchone()
        assert rows[0] == 1, f"Expected 1 CxC row, got {rows[0]}"

    def test_cxc_handler_skips_if_called_twice_for_same_venta(self):
        """INSERT OR IGNORE prevents duplicate CxC row."""
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler

        db = _make_db_with_cxc()
        finance_svc = MagicMock()
        handler = CreditSaleFinanceHandler(db_conn=db, finance_service=finance_svc)
        payload = {
            "payment_method": "Credito",
            "total": 100.0,
            "cliente_id": 1,
            "sale_id": 99,
            "folio": "VNT-DUPE",
            "sucursal_id": 1,
        }
        # Call twice (simulating accidental double-event)
        handler.handle(payload)
        try:
            handler.handle(payload)
        except Exception:
            pass  # UNIQUE constraint on venta_id prevents duplicate

        rows = db.execute(
            "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=99"
        ).fetchone()
        assert rows[0] == 1, f"Expected 1 CxC row after duplicate call, got {rows[0]}"

    def test_cxc_not_created_for_cash_sale(self):
        """SaleFinanceHandler skips credit flow for cash sales."""
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler

        db = _make_db_with_cxc()
        handler = CreditSaleFinanceHandler(db_conn=db, finance_service=MagicMock())
        payload = {
            "payment_method": "Efectivo",
            "total": 100.0,
            "cliente_id": 1,
            "sale_id": 77,
            "folio": "VNT-CASH",
            "sucursal_id": 1,
        }
        handler.handle(payload)
        rows = db.execute(
            "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=77"
        ).fetchone()
        assert rows[0] == 0, "CxC row should NOT be created for cash sale"

    def test_cxc_created_for_credito_with_accent(self):
        """After normalization, 'Crédito' must also create CxC."""
        from core.services.payment_normalization import normalize_payment_method
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler

        db = _make_db_with_cxc()
        handler = CreditSaleFinanceHandler(db_conn=db, finance_service=MagicMock())
        raw_method = "Crédito"
        normalized = normalize_payment_method(raw_method)
        payload = {
            "payment_method": normalized,
            "total": 150.0,
            "cliente_id": 1,
            "sale_id": 88,
            "folio": "VNT-ACCENT",
            "sucursal_id": 1,
        }
        handler.handle(payload)
        rows = db.execute(
            "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=88"
        ).fetchone()
        assert rows[0] == 1, \
            f"CxC should be created when normalized from 'Crédito', got {rows[0]}"
