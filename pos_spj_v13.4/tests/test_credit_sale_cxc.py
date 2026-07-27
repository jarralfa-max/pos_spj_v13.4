# tests/test_credit_sale_cxc.py — Credit sale CxC + validation regression tests
"""
Covers the four bugs found in Bug Report: "NO SE GENERA CxC DESDE POS":

BUG 1: CustomerCreditService not wired → SalesService.customer_service was None
BUG 2: CreditSaleFinanceHandler only updated credit_balance, not saldo
        → UI validation (reads saldo) always showed 0, never blocked
BUG 3: UI validation used wrong columns (saldo/limite_credito instead of
        credit_balance/credit_limit) and was advisory (dialog) not enforced
BUG 4: register_credit_sale also only updated credit_balance, not saldo
"""
from __future__ import annotations
import sqlite3
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE clientes (
            id             INTEGER PRIMARY KEY,
            nombre         TEXT,
            activo         INTEGER DEFAULT 1,
            credit_limit   REAL    DEFAULT 0,
            credit_balance REAL    DEFAULT 0,
            saldo          REAL    DEFAULT 0,
            limite_credito REAL    DEFAULT 0,
            puntos         INTEGER DEFAULT 0
        );
        CREATE TABLE cuentas_por_cobrar (
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
        CREATE TABLE financial_event_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            debe            TEXT,
            haber           TEXT,
            monto           REAL,
            evento          TEXT,
            concepto        TEXT,
            modulo          TEXT,
            referencia_id   INTEGER,
            sucursal_id     INTEGER,
            metadata        TEXT,
            created_at      DATETIME DEFAULT (datetime('now'))
        );
    """)
    conn.execute(
        "INSERT INTO clientes(id, nombre, activo, credit_limit, credit_balance, saldo, limite_credito) "
        "VALUES (1, 'Test Cliente', 1, 5000.0, 0.0, 0.0, 5000.0)"
    )
    conn.commit()
    return conn


class TrackedFinance:
    def __init__(self):
        self.calls = []
    def registrar_asiento(self, **kw):
        self.calls.append(kw)


# ---------------------------------------------------------------------------
# BUG 2 FIX: CreditSaleFinanceHandler updates BOTH credit_balance AND saldo
# ---------------------------------------------------------------------------

class TestCreditSaleHandlerSyncsColumns(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _run_handler(self, total=1000.0, cliente_id=1):
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler
        handler = CreditSaleFinanceHandler(db_conn=self.db, finance_service=self.finance)
        handler.handle({
            "payment_method": "Credito",
            "total":          total,
            "cliente_id":     cliente_id,
            "sale_id":        42,
            "folio":          "VNT-042",
            "branch_id":      1,
        })

    def test_cxc_row_created(self):
        """CxC INSERT must succeed."""
        self._run_handler()
        row = self.db.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0]
        self.assertEqual(row, 1)

    def test_credit_balance_incremented(self):
        """credit_balance must be incremented by sale total."""
        self._run_handler(total=1000.0)
        bal = self.db.execute(
            "SELECT credit_balance FROM clientes WHERE id=1"
        ).fetchone()[0]
        self.assertAlmostEqual(bal, 1000.0)

    def test_saldo_incremented(self):
        """BUG 2 FIX: saldo (legacy UI column) must ALSO be incremented."""
        self._run_handler(total=1000.0)
        saldo = self.db.execute(
            "SELECT saldo FROM clientes WHERE id=1"
        ).fetchone()[0]
        self.assertAlmostEqual(saldo, 1000.0,
            msg="saldo column must be kept in sync with credit_balance")

    def test_both_columns_equal_after_handler(self):
        """credit_balance and saldo must always be equal after a credit sale."""
        self._run_handler(total=2500.0)
        row = self.db.execute(
            "SELECT credit_balance, saldo FROM clientes WHERE id=1"
        ).fetchone()
        self.assertAlmostEqual(float(row[0]), float(row[1]))

    def test_gl_asiento_posted(self):
        """GL asiento 130.1-cuentas-por-cobrar / 401.0-ingresos-ventas must be posted."""
        self._run_handler(total=800.0)
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"],  "130.1-cuentas-por-cobrar")
        self.assertEqual(entry["haber"], "401.0-ingresos-ventas")
        self.assertAlmostEqual(entry["monto"], 800.0)


# ---------------------------------------------------------------------------
# BUG 4 FIX: CustomerCreditService.register_credit_sale syncs both columns
# ---------------------------------------------------------------------------

class TestRegisterCreditSaleSyncsColumns(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _svc(self):
        from application.services.customer_credit_service import CustomerCreditService
        svc = CustomerCreditService(db_conn=self.db, finance_service=self.finance)
        return svc

    def test_saldo_synced_on_register_credit_sale(self):
        """BUG 4 FIX: register_credit_sale must update saldo alongside credit_balance."""
        self._svc().register_credit_sale(
            cliente_id=1, sale_id=55, folio="F-055", monto=600.0, sucursal_id=1
        )
        row = self.db.execute(
            "SELECT credit_balance, saldo FROM clientes WHERE id=1"
        ).fetchone()
        self.assertAlmostEqual(float(row[0]), 600.0)
        self.assertAlmostEqual(float(row[1]), 600.0,
            msg="saldo must equal credit_balance after register_credit_sale")

    def test_cxc_row_inserted(self):
        self._svc().register_credit_sale(
            cliente_id=1, sale_id=56, folio="F-056", monto=300.0
        )
        row = self.db.execute("SELECT monto_original FROM cuentas_por_cobrar").fetchone()
        self.assertAlmostEqual(float(row[0]), 300.0)


# ---------------------------------------------------------------------------
# BUG 1 FIX: CustomerCreditService wired in app_container
# ---------------------------------------------------------------------------

class TestAppContainerWiresCustomerCreditService(unittest.TestCase):

    def test_customer_credit_service_instantiated(self):
        """app_container.py must create customer_credit_service."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "..", "core", "app_container.py",
        )).read()
        self.assertIn("CustomerCreditService", src,
            "app_container must import and instantiate CustomerCreditService")
        self.assertIn("customer_credit_service", src,
            "app_container must expose customer_credit_service attribute")

    def test_sales_service_receives_customer_service(self):
        """SalesService must be constructed with customer_service kwarg."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "..", "core", "app_container.py",
        )).read()
        # Find SalesService( block and verify customer_service is passed
        idx = src.find("SalesService(")
        self.assertGreater(idx, 0)
        # Find the closing ) of the constructor call (may span many lines)
        end = src.find("\n        )\n", idx)
        block = src[idx:end + 10] if end > 0 else src[idx:idx + 1200]
        self.assertIn("customer_service", block,
            "SalesService() call must include customer_service parameter")


# ---------------------------------------------------------------------------
# BUG 3 FIX: validate_credit uses credit_balance not saldo
# ---------------------------------------------------------------------------

class TestValidateCreditUsesCanonicalColumn(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()

    def _svc(self):
        from application.services.customer_credit_service import CustomerCreditService
        return CustomerCreditService(db_conn=self.db, finance_service=None)

    def test_validate_rejects_when_credit_balance_at_limit(self):
        """validate_credit must use credit_balance to compute disponible."""
        # Set credit_balance close to limit
        self.db.execute(
            "UPDATE clientes SET credit_balance=4500.0 WHERE id=1"
        )
        self.db.commit()

        ok, msg = self._svc().validate_credit(cliente_id=1, monto=600.0)
        self.assertFalse(ok)
        self.assertIn("600", msg)

    def test_validate_allows_when_within_limit(self):
        """Sale within credit limit must be approved."""
        # credit_balance=0, limit=5000 → monto=1000 is fine
        ok, msg = self._svc().validate_credit(cliente_id=1, monto=1000.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_validate_rejects_when_no_credit_limit(self):
        """Customer with credit_limit=0 must not be approved for credit sale."""
        self.db.execute("UPDATE clientes SET credit_limit=0 WHERE id=1")
        self.db.commit()
        ok, msg = self._svc().validate_credit(cliente_id=1, monto=100.0)
        self.assertFalse(ok)

    def test_validate_rejects_unknown_client(self):
        ok, msg = self._svc().validate_credit(cliente_id=9999, monto=100.0)
        self.assertFalse(ok)

    def test_source_reads_credit_balance_not_saldo(self):
        """CustomerCreditService.validate_credit must query credit_balance column."""
        import os, inspect
        from application.services.customer_credit_service import CustomerCreditService
        src = inspect.getsource(CustomerCreditService.validate_credit)
        self.assertIn("credit_balance", src,
            "validate_credit must query credit_balance")

    def test_ui_source_uses_canonical_columns(self):
        """modulos/ventas.py credit validation must read credit_balance."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "..", "modulos", "ventas.py",
        )).read()
        self.assertIn("credit_balance", src,
            "ventas.py credit validation must reference credit_balance column")
        self.assertIn("customer_credit_service", src,
            "ventas.py must delegate to customer_credit_service when available")


if __name__ == "__main__":
    unittest.main(verbosity=2)
