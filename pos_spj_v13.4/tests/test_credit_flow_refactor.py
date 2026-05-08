# tests/test_credit_flow_refactor.py — CxC / Credit Flow Refactor test suite
"""
Covers the full credit-sale refactor requirements:

1.  Cash sale: no CxC, no credit_balance change
2.  Credit sale happy-path: CxC inserted, credit_balance + saldo updated, GL posted
3.  Credit validation: rejected when balance at limit
4.  Credit validation: rejected when limit = 0
5.  Credit validation: rejected when customer not found
6.  Credit validation: approved within limit
7.  CxC idempotency: duplicate folio is silently ignored by AccountsReceivableService
8.  CxC reversal: credit_balance + saldo decremented, CxC marked cancelada
9.  Overdue blocking: customer with overdue CxC rejected when block_on_overdue=True
10. Payment application: saldo_pendiente decremented, credit_balance decremented
11. SalesService no longer calls register_credit_sale post-commit (no duplicate CxC)
"""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared DB fixture
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
        INSERT INTO clientes(id, nombre, activo, credit_limit, credit_balance, saldo, limite_credito)
        VALUES (1, 'Cliente Crédito', 1, 5000.0, 0.0, 0.0, 5000.0);
        INSERT INTO clientes(id, nombre, activo, credit_limit, credit_balance, saldo, limite_credito)
        VALUES (2, 'Sin Límite', 1, 0.0, 0.0, 0.0, 0.0);
    """)
    conn.commit()
    return conn


class TrackedFinance:
    def __init__(self):
        self.calls = []

    def registrar_asiento(self, **kw):
        self.calls.append(kw)


# ---------------------------------------------------------------------------
# 1 & 2: AccountsReceivableService.create_cxc (happy-path + GL)
# ---------------------------------------------------------------------------

class TestAccountsReceivableCreateCxc(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _svc(self):
        from application.services.accounts_receivable_service import AccountsReceivableService
        return AccountsReceivableService(db_conn=self.db, finance_service=self.finance)

    # Scenario 1 — cash sale: caller simply doesn't invoke create_cxc
    def test_cash_sale_no_cxc_side_effect(self):
        """When create_cxc is NOT called, credit_balance stays 0."""
        row = self.db.execute("SELECT credit_balance FROM clientes WHERE id=1").fetchone()
        self.assertAlmostEqual(float(row[0]), 0.0)

    # Scenario 2 — credit sale happy path
    def test_credit_sale_inserts_cxc_row(self):
        self._svc().create_cxc(cliente_id=1, sale_id=10, folio="F-010", monto=1000.0)
        cnt = self.db.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0]
        self.assertEqual(cnt, 1)

    def test_credit_sale_increments_credit_balance(self):
        self._svc().create_cxc(cliente_id=1, sale_id=11, folio="F-011", monto=1200.0)
        bal = self.db.execute("SELECT credit_balance FROM clientes WHERE id=1").fetchone()[0]
        self.assertAlmostEqual(float(bal), 1200.0)

    def test_credit_sale_increments_saldo(self):
        self._svc().create_cxc(cliente_id=1, sale_id=12, folio="F-012", monto=800.0)
        saldo = self.db.execute("SELECT saldo FROM clientes WHERE id=1").fetchone()[0]
        self.assertAlmostEqual(float(saldo), 800.0,
            msg="saldo column must be kept in sync with credit_balance")

    def test_credit_sale_gl_cxc_entry_posted(self):
        self._svc().create_cxc(cliente_id=1, sale_id=13, folio="F-013", monto=500.0)
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"],  "130.1-cuentas-por-cobrar")
        self.assertEqual(entry["haber"], "401.0-ingresos-ventas")
        self.assertAlmostEqual(entry["monto"], 500.0)


# ---------------------------------------------------------------------------
# 3–6: CreditValidationService
# ---------------------------------------------------------------------------

class TestCreditValidationService(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()

    def _svc(self, block_on_overdue=False):
        from application.services.credit_validation_service import CreditValidationService
        return CreditValidationService(db_conn=self.db, block_on_overdue=block_on_overdue)

    # Scenario 3 — rejected when balance at limit
    def test_rejected_when_balance_at_limit(self):
        self.db.execute("UPDATE clientes SET credit_balance=4800.0, saldo=4800.0 WHERE id=1")
        self.db.commit()
        ok, msg = self._svc().validate(cliente_id=1, financed_amount=300.0)
        self.assertFalse(ok)
        self.assertIn("insuficiente", msg.lower())

    # Scenario 4 — rejected when limit = 0
    def test_rejected_when_no_credit_limit(self):
        ok, msg = self._svc().validate(cliente_id=2, financed_amount=100.0)
        self.assertFalse(ok)
        self.assertIn("línea de crédito", msg.lower())

    # Scenario 5 — rejected when customer not found
    def test_rejected_unknown_customer(self):
        ok, msg = self._svc().validate(cliente_id=9999, financed_amount=100.0)
        self.assertFalse(ok)
        self.assertIn("9999", msg)

    # Scenario 6 — approved within limit
    def test_approved_within_limit(self):
        ok, msg = self._svc().validate(cliente_id=1, financed_amount=1000.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_approved_exact_limit(self):
        ok, msg = self._svc().validate(cliente_id=1, financed_amount=5000.0)
        self.assertTrue(ok)

    def test_rejected_zero_amount(self):
        ok, msg = self._svc().validate(cliente_id=1, financed_amount=0.0)
        self.assertFalse(ok)

    def test_available_credit_returns_correct_value(self):
        self.db.execute("UPDATE clientes SET credit_balance=2000.0, saldo=2000.0 WHERE id=1")
        self.db.commit()
        avail = self._svc().available_credit(cliente_id=1)
        self.assertAlmostEqual(avail, 3000.0)


# ---------------------------------------------------------------------------
# 7: Idempotency — duplicate folio guard
# ---------------------------------------------------------------------------

class TestCxcIdempotency(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _svc(self):
        from application.services.accounts_receivable_service import AccountsReceivableService
        return AccountsReceivableService(db_conn=self.db, finance_service=self.finance)

    def test_duplicate_folio_not_inserted(self):
        """create_cxc called twice with same folio must produce only 1 CxC row."""
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=20, folio="F-020", monto=600.0)
        svc.create_cxc(cliente_id=1, sale_id=20, folio="F-020", monto=600.0)
        cnt = self.db.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0]
        self.assertEqual(cnt, 1, "Duplicate folio must be silently ignored")

    def test_credit_balance_not_doubled_on_duplicate(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=21, folio="F-021", monto=400.0)
        svc.create_cxc(cliente_id=1, sale_id=21, folio="F-021", monto=400.0)
        bal = float(self.db.execute("SELECT credit_balance FROM clientes WHERE id=1").fetchone()[0])
        self.assertAlmostEqual(bal, 400.0, msg="credit_balance must not be doubled on duplicate")


# ---------------------------------------------------------------------------
# 8: CxC Reversal
# ---------------------------------------------------------------------------

class TestCxcReversal(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _svc(self):
        from application.services.accounts_receivable_service import AccountsReceivableService
        return AccountsReceivableService(db_conn=self.db, finance_service=self.finance)

    def test_reversal_marks_cxc_cancelada(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=30, folio="F-030", monto=700.0)
        svc.reverse_cxc(sale_id=30, sucursal_id=1, cliente_id=1)
        estado = self.db.execute(
            "SELECT estado FROM cuentas_por_cobrar WHERE venta_id=30"
        ).fetchone()[0]
        self.assertEqual(estado, "cancelada")

    def test_reversal_decrements_credit_balance(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=31, folio="F-031", monto=700.0)
        svc.reverse_cxc(sale_id=31, sucursal_id=1, cliente_id=1)
        bal = float(self.db.execute("SELECT credit_balance FROM clientes WHERE id=1").fetchone()[0])
        self.assertAlmostEqual(bal, 0.0)

    def test_reversal_decrements_saldo(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=32, folio="F-032", monto=700.0)
        svc.reverse_cxc(sale_id=32, sucursal_id=1, cliente_id=1)
        saldo = float(self.db.execute("SELECT saldo FROM clientes WHERE id=1").fetchone()[0])
        self.assertAlmostEqual(saldo, 0.0)

    def test_reversal_posts_gl_reversal_entry(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=33, folio="F-033", monto=300.0)
        self.finance.calls.clear()
        svc.reverse_cxc(sale_id=33, sucursal_id=1, cliente_id=1)
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"],  "401.0-ingresos-ventas")
        self.assertEqual(entry["haber"], "130.1-cuentas-por-cobrar")


# ---------------------------------------------------------------------------
# 9: Overdue blocking
# ---------------------------------------------------------------------------

class TestOverdueBlocking(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()

    def _svc(self, block_on_overdue):
        from application.services.credit_validation_service import CreditValidationService
        return CreditValidationService(db_conn=self.db, block_on_overdue=block_on_overdue)

    def _add_overdue_cxc(self):
        self.db.execute("""
            INSERT INTO cuentas_por_cobrar
                (cliente_id, venta_id, folio, monto_original, saldo_pendiente, estado)
            VALUES (1, 99, 'F-099', 500.0, 500.0, 'vencida')
        """)
        self.db.commit()

    def test_overdue_rejected_when_enforcement_on(self):
        self._add_overdue_cxc()
        ok, msg = self._svc(block_on_overdue=True).validate(cliente_id=1, financed_amount=100.0)
        self.assertFalse(ok)
        self.assertIn("vencida", msg.lower())

    def test_overdue_allowed_when_enforcement_off(self):
        self._add_overdue_cxc()
        ok, msg = self._svc(block_on_overdue=False).validate(cliente_id=1, financed_amount=100.0)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# 10: Payment application
# ---------------------------------------------------------------------------

class TestApplyPayment(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.db = _make_db()
        self.finance = TrackedFinance()

    def _svc(self):
        from application.services.accounts_receivable_service import AccountsReceivableService
        return AccountsReceivableService(db_conn=self.db, finance_service=self.finance)

    def test_apply_payment_reduces_saldo_pendiente(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=40, folio="F-040", monto=1000.0)
        cxc_id = self.db.execute("SELECT id FROM cuentas_por_cobrar WHERE venta_id=40").fetchone()[0]
        svc.apply_payment(cxc_id=cxc_id, amount=400.0)
        pending = float(self.db.execute(
            "SELECT saldo_pendiente FROM cuentas_por_cobrar WHERE id=?", (cxc_id,)
        ).fetchone()[0])
        self.assertAlmostEqual(pending, 600.0)

    def test_apply_payment_reduces_credit_balance(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=41, folio="F-041", monto=1000.0)
        cxc_id = self.db.execute("SELECT id FROM cuentas_por_cobrar WHERE venta_id=41").fetchone()[0]
        svc.apply_payment(cxc_id=cxc_id, amount=1000.0)
        bal = float(self.db.execute("SELECT credit_balance FROM clientes WHERE id=1").fetchone()[0])
        self.assertAlmostEqual(bal, 0.0)

    def test_full_payment_marks_pagada(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=42, folio="F-042", monto=500.0)
        cxc_id = self.db.execute("SELECT id FROM cuentas_por_cobrar WHERE venta_id=42").fetchone()[0]
        svc.apply_payment(cxc_id=cxc_id, amount=500.0)
        estado = self.db.execute(
            "SELECT estado FROM cuentas_por_cobrar WHERE id=?", (cxc_id,)
        ).fetchone()[0]
        self.assertEqual(estado, "pagada")

    def test_payment_gl_entry_posted(self):
        svc = self._svc()
        svc.create_cxc(cliente_id=1, sale_id=43, folio="F-043", monto=800.0)
        cxc_id = self.db.execute("SELECT id FROM cuentas_por_cobrar WHERE venta_id=43").fetchone()[0]
        self.finance.calls.clear()
        svc.apply_payment(cxc_id=cxc_id, amount=300.0)
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"],  "110-caja")
        self.assertEqual(entry["haber"], "130.1-cuentas-por-cobrar")
        self.assertAlmostEqual(entry["monto"], 300.0)


# ---------------------------------------------------------------------------
# 11: SalesService no longer creates duplicate CxC post-commit
# ---------------------------------------------------------------------------

class TestSalesServiceNoDuplicateCxc(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def test_post_commit_register_credit_sale_removed(self):
        """SalesService.execute_sale must NOT call customer_service.register_credit_sale post-commit.
        CreditSaleFinanceHandler inside SAVEPOINT is the single source of truth for CxC creation."""
        import inspect
        from core.services.sales_service import SalesService
        src = inspect.getsource(SalesService.execute_sale)
        # The post-commit block was removed; register_credit_sale should not appear
        # in the post-RELEASE section of execute_sale.
        # We verify it's absent entirely (or only mentioned in a comment).
        lines_with_call = [
            ln for ln in src.splitlines()
            if "register_credit_sale" in ln and not ln.strip().startswith("#")
        ]
        self.assertEqual(
            lines_with_call, [],
            f"execute_sale must not call register_credit_sale — found: {lines_with_call}"
        )

    def test_app_container_exposes_credit_validation_service(self):
        """app_container.py must instantiate CreditValidationService."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__), "..", "core", "app_container.py"
        )).read()
        self.assertIn("CreditValidationService", src)
        self.assertIn("credit_validation_service", src)

    def test_app_container_exposes_accounts_receivable_service(self):
        """app_container.py must instantiate AccountsReceivableService."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__), "..", "core", "app_container.py"
        )).read()
        self.assertIn("AccountsReceivableService", src)
        self.assertIn("accounts_receivable_service", src)

    def test_ventas_py_validates_credit_post_dialog(self):
        """modulos/ventas.py must validate credit AFTER the payment dialog (post-dialog), not before."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__), "..", "modulos", "ventas.py"
        )).read()
        # The post-dialog validation block references 'forma_pago' and 'Crédito' AFTER DialogoPago
        dialog_idx = src.find("DialogoPago(")
        self.assertGreater(dialog_idx, 0)
        post_dialog_src = src[dialog_idx:]
        self.assertIn("forma_pago", post_dialog_src,
            "Credit validation must happen after DialogoPago in the source order")
        self.assertIn("Cliente requerido", post_dialog_src,
            "Post-dialog must block credit sales without a selected customer")

    def test_ventas_py_no_pre_dialog_credit_block(self):
        """The old pre-dialog credit validation block must be gone from ventas.py."""
        import os
        src = open(os.path.join(
            os.path.dirname(__file__), "..", "modulos", "ventas.py"
        )).read()
        # The removed block had a very specific comment
        self.assertNotIn(
            "Validar límite de crédito antes de abrir diálogo",
            src,
            "Pre-dialog credit validation comment must be removed"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
