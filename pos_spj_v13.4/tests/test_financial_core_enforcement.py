# tests/test_financial_core_enforcement.py — SPJ ERP Financial Core Audit 2026-05-08
"""
Regression tests for the Financial Core Enforcement audit.

Covers the six critical fixes applied:
  1. No double GL posting on purchases (removed _compra_egreso/_compra_stock from wiring)
  2. CreditSaleFinanceHandler — CxC + GL inside SAVEPOINT for credit sales
  3. SaleCancelledFinanceHandler — GL reversal on sale cancellation
  4. CustomerCreditService.register_credit_sale — GL asiento before commit
  5. CierreCajaService.corte_z — asiento for cash discrepancies
  6. AnticipoCotizacionService.registrar_anticipo_pagado — asiento for advance payments
"""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import MagicMock, call, patch


def approx(expected, abs=1e-6):
    """Minimal pytest.approx replacement for float comparisons."""
    class _Approx:
        def __eq__(self, actual):
            return abs_(actual - expected) <= abs_tol
        def __repr__(self):
            return f"approx({expected}, abs={abs_tol})"
    import builtins
    abs_ = builtins.abs
    abs_tol = abs
    return _Approx()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _memory_db() -> sqlite3.Connection:
    """In-memory SQLite with Row factory and WAL disabled (no WAL in :memory:)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id      INTEGER NOT NULL,
            venta_id        INTEGER,
            folio           TEXT,
            monto_original  REAL    NOT NULL,
            saldo_pendiente REAL    NOT NULL,
            estado          TEXT    DEFAULT 'pendiente',
            sucursal_id     INTEGER DEFAULT 1,
            fecha           DATETIME DEFAULT (datetime('now')),
            fecha_pago      DATETIME
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id             INTEGER PRIMARY KEY,
            nombre         TEXT,
            activo         INTEGER DEFAULT 1,
            credit_limit   REAL DEFAULT 0,
            credit_balance REAL DEFAULT 0,
            saldo          REAL DEFAULT 0,
            limite_credito REAL DEFAULT 0,
            puntos         INTEGER DEFAULT 0,
            allows_credit  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            concepto    TEXT,
            monto       REAL,
            modulo      TEXT,
            evento      TEXT,
            sucursal_id INTEGER DEFAULT 1,
            fecha       DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            folio       TEXT,
            total       REAL,
            estado      TEXT DEFAULT 'completada',
            sucursal_id INTEGER DEFAULT 1,
            forma_pago  TEXT DEFAULT 'Efectivo',
            fecha       DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cierres_caja (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid             TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
            tipo             TEXT DEFAULT 'Z',
            sucursal_id      INTEGER DEFAULT 1,
            usuario          TEXT,
            turno            TEXT,
            fecha_apertura   DATETIME,
            fecha_cierre     DATETIME DEFAULT (datetime('now')),
            total_ventas     REAL DEFAULT 0,
            num_ventas       INTEGER DEFAULT 0,
            total_efectivo   REAL DEFAULT 0,
            total_tarjeta    REAL DEFAULT 0,
            total_transferencia REAL DEFAULT 0,
            total_otros      REAL DEFAULT 0,
            total_anulaciones REAL DEFAULT 0,
            num_anulaciones  INTEGER DEFAULT 0,
            efectivo_contado REAL DEFAULT 0,
            fondo_inicial    REAL DEFAULT 0,
            diferencia       REAL DEFAULT 0,
            comentarios      TEXT,
            estado           TEXT DEFAULT 'cerrado'
        );
        CREATE TABLE IF NOT EXISTS turno_actual (
            sucursal_id    INTEGER PRIMARY KEY,
            usuario        TEXT,
            turno          TEXT,
            fondo_inicial  REAL DEFAULT 0,
            fecha_apertura DATETIME,
            abierto        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ordenes_cotizacion (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_orden         TEXT UNIQUE,
            cotizacion_id        INTEGER,
            cliente_id           INTEGER,
            sucursal_id          INTEGER DEFAULT 1,
            estado               TEXT DEFAULT 'anticipo_pendiente',
            requiere_anticipo    INTEGER DEFAULT 0,
            pct_anticipo_aplicado REAL DEFAULT 0,
            razon_anticipo       TEXT,
            monto_anticipo       REAL DEFAULT 0,
            anticipo_pagado      REAL DEFAULT 0,
            metodo_anticipo      TEXT,
            payment_id           TEXT,
            fecha_entrega        TEXT,
            hora_entrega         TEXT,
            tipo_entrega         TEXT,
            notas                TEXT,
            usuario_asigno       TEXT
        );
    """)
    conn.commit()
    return conn


def _mock_finance():
    """Finance service mock that records registrar_asiento calls."""
    fs = MagicMock()
    fs.registrar_asiento = MagicMock()
    return fs


# ── 1. Double GL fix: _compra_egreso removed ─────────────────────────────────

class TestNoPurchaseDoubleGL(unittest.TestCase):
    """Verify _compra_egreso is no longer wired on COMPRA_REGISTRADA."""

    def test_wire_flujos_criticos_has_no_active_subscriptions(self):
        """_wire_flujos_criticos must be a no-op (pass) after the audit fix."""
        from core.events.wiring import _wire_flujos_criticos

        bus     = MagicMock()
        container = MagicMock()
        _wire_flujos_criticos(bus, container)

        bus.subscribe.assert_not_called()

    def test_purchase_finance_handler_subscribes_once(self):
        """PurchaseFinanceHandler registers exactly once on PURCHASE_CREATED."""
        from core.events.wiring import _wire_purchase_items_handlers
        from core.events.domain_events import PURCHASE_CREATED

        bus = MagicMock()
        container = MagicMock()
        container.inventory_service = None   # disable inv handler to isolate
        container.finance_service   = _mock_finance()

        _wire_purchase_items_handlers(bus, container)

        finance_subs = [c for c in bus.subscribe.call_args_list
                        if c.args[0] == PURCHASE_CREATED]
        assert len(finance_subs) == 1, (
            f"PurchaseFinanceHandler must register exactly once; got {len(finance_subs)}"
        )


# ── 2. CreditSaleFinanceHandler ───────────────────────────────────────────────

class TestCreditSaleFinanceHandler(unittest.TestCase):

    def setUp(self):
        self.db = _memory_db()
        self.db.execute(
            "INSERT INTO clientes (id, nombre, credit_limit, credit_balance) VALUES (1,'Ana',5000,0)"
        )
        self.db.commit()
        self.fs = _mock_finance()

    def _handler(self):
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler
        return CreditSaleFinanceHandler(db_conn=self.db, finance_service=self.fs)

    def test_credit_sale_creates_cxc_record(self):
        handler = self._handler()
        handler.handle({
            "payment_method": "Credito",
            "total": 1200.0,
            "cliente_id": 1,
            "sale_id": 42,
            "folio": "VNT-001",
            "sucursal_id": 1,
        })
        row = self.db.execute(
            "SELECT saldo_pendiente, estado FROM cuentas_por_cobrar WHERE venta_id=42"
        ).fetchone()
        assert row is not None, "CxC record must be created for credit sale"
        assert float(row["saldo_pendiente"]) == 1200.0
        assert row["estado"] == "pendiente"

    def test_credit_sale_increments_client_balance(self):
        handler = self._handler()
        handler.handle({
            "payment_method": "Credito",
            "total": 800.0,
            "cliente_id": 1,
            "sale_id": 43,
            "folio": "VNT-002",
            "sucursal_id": 1,
        })
        row = self.db.execute(
            "SELECT credit_balance FROM clientes WHERE id=1"
        ).fetchone()
        assert float(row["credit_balance"]) == 800.0

    def test_credit_sale_registers_ledger_entry(self):
        handler = self._handler()
        handler.handle({
            "payment_method": "Credito",
            "total": 500.0,
            "cliente_id": 1,
            "sale_id": 44,
            "folio": "VNT-003",
            "sucursal_id": 1,
        })
        self.fs.registrar_asiento.assert_called_once()
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert "130.1-cuentas-por-cobrar" in kwargs["debe"]
        assert "401.0-ingresos-ventas" in kwargs["haber"]
        assert kwargs["monto"] == 500.0
        assert kwargs["evento"] == "VENTA_CREDITO"

    def test_cash_sale_ignored(self):
        """Handler must be a no-op for non-credit payment methods."""
        handler = self._handler()
        handler.handle({
            "payment_method": "Efectivo",
            "total": 300.0,
            "cliente_id": 1,
            "sale_id": 45,
            "folio": "VNT-004",
        })
        self.fs.registrar_asiento.assert_not_called()
        row = self.db.execute(
            "SELECT id FROM cuentas_por_cobrar WHERE venta_id=45"
        ).fetchone()
        assert row is None

    def test_reraises_on_failure(self):
        """Handler re-raises so the SAVEPOINT rolls back."""
        self.fs.registrar_asiento.side_effect = RuntimeError("DB locked")
        handler = self._handler()
        with self.assertRaises(RuntimeError):
            handler.handle({
                "payment_method": "Credito",
                "total": 200.0,
                "cliente_id": 1,
                "sale_id": 46,
                "folio": "VNT-005",
                "sucursal_id": 1,
            })


# ── 3. SaleCancelledFinanceHandler ────────────────────────────────────────────

class TestSaleCancelledFinanceHandler(unittest.TestCase):

    def setUp(self):
        self.db = _memory_db()
        # Pre-create CxC record for credit sale cancellation test
        self.db.execute(
            "INSERT INTO clientes (id, nombre, credit_balance) VALUES (1,'Bob',1000)"
        )
        self.db.execute(
            "INSERT INTO cuentas_por_cobrar "
            "(cliente_id,venta_id,folio,monto_original,saldo_pendiente,sucursal_id) "
            "VALUES (1,10,'VNT-010',1000,1000,1)"
        )
        self.db.commit()
        self.fs = _mock_finance()

    def _handler(self):
        from core.events.handlers.finance_handler import SaleCancelledFinanceHandler
        return SaleCancelledFinanceHandler(db_conn=self.db, finance_service=self.fs)

    def test_cash_sale_cancellation_posts_reversal(self):
        handler = self._handler()
        handler.handle({
            "venta_id": 99,
            "folio": "VNT-099",
            "total": 300.0,
            "payment_method": "Efectivo",
            "sucursal_id": 1,
        })
        self.fs.registrar_asiento.assert_called_once()
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["debe"] == "401.0-ingresos-ventas"
        assert kwargs["haber"] == "110-caja"
        assert kwargs["monto"] == 300.0
        assert kwargs["evento"] == "VENTA_CANCELADA"

    def test_credit_sale_cancellation_reverses_cxc(self):
        handler = self._handler()
        handler.handle({
            "venta_id": 10,
            "folio": "VNT-010",
            "total": 1000.0,
            "payment_method": "Credito",
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        # CxC should be marked cancelled
        row = self.db.execute(
            "SELECT estado, saldo_pendiente FROM cuentas_por_cobrar WHERE venta_id=10"
        ).fetchone()
        assert row["estado"] == "cancelada"
        assert float(row["saldo_pendiente"]) == 0.0

        # Client balance decremented
        bal = self.db.execute(
            "SELECT credit_balance FROM clientes WHERE id=1"
        ).fetchone()
        assert float(bal["credit_balance"]) == 0.0

        # GL reversal posted with CxC account
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["haber"] == "130.1-cuentas-por-cobrar"

    def test_zero_total_skipped(self):
        handler = self._handler()
        handler.handle({"venta_id": 1, "total": 0.0, "payment_method": "Efectivo"})
        self.fs.registrar_asiento.assert_not_called()


# ── 4. CustomerCreditService atomicity ───────────────────────────────────────

class TestCustomerCreditServiceAtomicity(unittest.TestCase):
    """registrar_asiento must be called BEFORE commit — if it fails, CxC is not persisted."""

    def setUp(self):
        self.db = _memory_db()
        self.db.execute(
            "INSERT INTO clientes (id, nombre, credit_balance) VALUES (5,'Carlos',0)"
        )
        self.db.commit()

    def _svc(self, fs):
        from application.services.customer_credit_service import CustomerCreditService
        return CustomerCreditService(db_conn=self.db, finance_service=fs)

    def test_asiento_called_before_commit(self):
        """registrar_asiento must appear before db.commit in the call sequence."""
        call_order = []

        class TrackedConn:
            """Thin wrapper that records asiento/commit ordering."""
            def __init__(self, conn):
                self._conn = conn
            def execute(self, *a, **kw):
                return self._conn.execute(*a, **kw)
            def commit(self):
                call_order.append("commit")
                self._conn.commit()
            def rollback(self):
                self._conn.rollback()
            def executescript(self, *a, **kw):
                return self._conn.executescript(*a, **kw)

        wrapped = TrackedConn(self.db)

        fs = _mock_finance()
        def tracked_asiento(**kwargs):
            call_order.append("asiento")
        fs.registrar_asiento.side_effect = tracked_asiento

        from application.services.customer_credit_service import CustomerCreditService
        svc = CustomerCreditService(db_conn=wrapped, finance_service=fs)
        svc.register_credit_sale(5, 100, "VNT-100", 500.0, sucursal_id=1)

        assert "asiento" in call_order, "registrar_asiento must be called"
        assert "commit" in call_order, "db.commit must be called"
        # _ensure_cxc_table() in __init__ emits an early commit; we care that
        # registrar_asiento precedes the LAST commit (the one in register_credit_sale).
        last_commit_idx  = len(call_order) - 1 - call_order[::-1].index("commit")
        asiento_idx      = call_order.index("asiento")
        assert asiento_idx < last_commit_idx, (
            f"registrar_asiento must be called BEFORE the final db.commit(); "
            f"call_order={call_order}"
        )

    def test_cxc_persisted_on_success(self):
        svc = self._svc(_mock_finance())
        svc.register_credit_sale(5, 101, "VNT-101", 750.0, sucursal_id=1)
        row = self.db.execute(
            "SELECT saldo_pendiente FROM cuentas_por_cobrar WHERE venta_id=101"
        ).fetchone()
        assert row is not None
        assert float(row["saldo_pendiente"]) == 750.0


# ── 5. CierreCajaService corte Z discrepancy asiento ─────────────────────────

class TestCierreCajaDiscrepancyAsiento(unittest.TestCase):

    def setUp(self):
        self.db = _memory_db()
        # Open a shift
        self.db.execute(
            "INSERT INTO turno_actual (sucursal_id, usuario, turno, fondo_inicial, "
            "fecha_apertura, abierto) VALUES (1,'cajero1','Mañana',100,datetime('now'),1)"
        )
        # Add a completed cash sale
        self.db.execute(
            "INSERT INTO ventas (folio,total,estado,sucursal_id,forma_pago,fecha) "
            "VALUES ('V001',500,'completada',1,'Efectivo',datetime('now'))"
        )
        self.db.commit()
        self.fs = _mock_finance()

    def _svc(self):
        from core.services.cierre_caja_service import CierreCajaService
        return CierreCajaService(conn=self.db, sucursal_id=1,
                                  usuario="cajero1", finance_service=self.fs)

    def test_surplus_posts_asiento(self):
        """Efectivo_contado > expected → sobrante → asiento debe=caja haber=diferencias."""
        svc = self._svc()
        # Expected: 500 (ventas) + 100 (fondo) = 600; countado 650 → +50 surplus
        result = svc.corte_z(efectivo_contado=650.0)
        assert result["diferencia"] == approx(50.0, abs=0.01)
        self.fs.registrar_asiento.assert_called_once()
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["debe"] == "110-caja"
        assert kwargs["haber"] == "999-diferencias-caja"
        assert kwargs["monto"] == approx(50.0, abs=0.01)
        assert kwargs["evento"] == "CORTE_Z"

    def test_shortage_posts_asiento(self):
        """Efectivo_contado < expected → faltante → asiento debe=diferencias haber=caja."""
        svc = self._svc()
        result = svc.corte_z(efectivo_contado=580.0)
        assert result["diferencia"] == approx(-20.0, abs=0.01)
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["debe"] == "999-diferencias-caja"
        assert kwargs["haber"] == "110-caja"
        assert kwargs["monto"] == approx(20.0, abs=0.01)

    def test_zero_difference_skips_asiento(self):
        """Exact cash count produces no asiento."""
        svc = self._svc()
        result = svc.corte_z(efectivo_contado=600.0)
        assert result["diferencia"] == approx(0.0, abs=0.01)
        self.fs.registrar_asiento.assert_not_called()

    def test_corte_z_without_finance_service_does_not_crash(self):
        from core.services.cierre_caja_service import CierreCajaService
        svc = CierreCajaService(conn=self.db, sucursal_id=1, usuario="cajero1")
        result = svc.corte_z(efectivo_contado=620.0)
        # Should complete without error even if no finance_service
        assert "cierre_id" in result


# ── 6. AnticipoCotizacionService asiento ─────────────────────────────────────

class TestAnticipoAsiento(unittest.TestCase):

    def setUp(self):
        self.db = _memory_db()
        self.db.execute("""
            INSERT INTO ordenes_cotizacion
              (numero_orden, cotizacion_id, cliente_id, sucursal_id,
               monto_anticipo, anticipo_pagado, estado)
            VALUES ('ORD-001', 1, 7, 1, 1000.0, 0.0, 'anticipo_pendiente')
        """)
        self.db.commit()
        self.fs = _mock_finance()

    def _svc(self):
        from core.services.anticipo_service import AnticipoCotizacionService
        return AnticipoCotizacionService(db_conn=self.db, finance_service=self.fs)

    def test_efectivo_anticipo_posts_caja_haber_anticipos(self):
        svc = self._svc()
        svc.registrar_anticipo_pagado("ORD-001", 500.0, "Efectivo", sucursal_id=1)
        self.fs.registrar_asiento.assert_called_once()
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["debe"] == "110-caja"
        assert kwargs["haber"] == "217-anticipos-de-clientes"
        assert kwargs["monto"] == 500.0
        assert kwargs["evento"] == "ANTICIPO_PAGADO"

    def test_transferencia_anticipo_posts_banco(self):
        svc = self._svc()
        svc.registrar_anticipo_pagado("ORD-001", 300.0, "Transferencia", sucursal_id=1)
        kwargs = self.fs.registrar_asiento.call_args.kwargs
        assert kwargs["debe"] == "112-banco"

    def test_anticipo_updates_orden_estado(self):
        svc = self._svc()
        svc.registrar_anticipo_pagado("ORD-001", 1000.0, "Efectivo", sucursal_id=1)
        row = self.db.execute(
            "SELECT estado, anticipo_pagado FROM ordenes_cotizacion WHERE numero_orden='ORD-001'"
        ).fetchone()
        assert row["estado"] == "en_preparacion"
        assert float(row["anticipo_pagado"]) == 1000.0

    def test_anticipo_finance_failure_does_not_crash(self):
        """Finance failure logs but does not propagate — orden state must still update."""
        self.fs.registrar_asiento.side_effect = RuntimeError("timeout")
        svc = self._svc()
        svc.registrar_anticipo_pagado("ORD-001", 200.0, "Efectivo", sucursal_id=1)
        row = self.db.execute(
            "SELECT anticipo_pagado FROM ordenes_cotizacion WHERE numero_orden='ORD-001'"
        ).fetchone()
        assert float(row["anticipo_pagado"]) == 200.0

    def test_no_finance_service_does_not_crash(self):
        from core.services.anticipo_service import AnticipoCotizacionService
        svc = AnticipoCotizacionService(db_conn=self.db)
        svc.registrar_anticipo_pagado("ORD-001", 100.0, "Efectivo")
        row = self.db.execute(
            "SELECT anticipo_pagado FROM ordenes_cotizacion WHERE numero_orden='ORD-001'"
        ).fetchone()
        assert float(row["anticipo_pagado"]) == 100.0
