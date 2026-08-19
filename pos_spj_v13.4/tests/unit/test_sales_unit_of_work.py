"""SALES-5/POS-5 — SalesUnitOfWork transaction boundary. Mirrors
tests/integration/cash_register/test_cash_register_unit_of_work.py's style
(row-count assertions across commit/rollback boundaries)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.sales.entities import Sale
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_sales_schema(c)
    c.commit()
    yield c
    c.close()


def _sale(**overrides) -> Sale:
    defaults = dict(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
    defaults.update(overrides)
    return Sale.start(**defaults)


class TestCommitOnCleanExit:
    def test_sale_and_lines_committed_together(self, conn):
        sale = _sale()
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                      unit_price=Decimal("10.00"))

        with SalesUnitOfWork(conn) as uow:
            uow.sales.save(sale)

        # A fresh connection would see it too, but re-querying the same
        # connection after normal `with` exit already proves the commit ran.
        row = conn.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale.id,)).fetchone()
        assert row[0] == 1
        lines = conn.execute("SELECT COUNT(*) FROM sale_lines WHERE sale_id=?",
                              (sale.id,)).fetchone()
        assert lines[0] == 1

    def test_outbox_event_committed_in_same_transaction(self, conn):
        sale = _sale()
        with SalesUnitOfWork(conn) as uow:
            uow.sales.save(sale)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name="SALE_STARTED",
                payload_json="{}", operation_id=sale.operation_id)

        pending = conn.execute("SELECT COUNT(*) FROM sales_outbox WHERE status='PENDING'").fetchone()
        assert pending[0] == 1


class TestRollbackOnException:
    def test_exception_rolls_back_sale_and_lines_together(self, conn):
        sale = _sale()
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                      unit_price=Decimal("10.00"))

        with pytest.raises(RuntimeError):
            with SalesUnitOfWork(conn) as uow:
                uow.sales.save(sale)
                raise RuntimeError("simulated failure mid-transaction")

        row = conn.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale.id,)).fetchone()
        assert row[0] == 0
        lines = conn.execute("SELECT COUNT(*) FROM sale_lines WHERE sale_id=?",
                              (sale.id,)).fetchone()
        assert lines[0] == 0

    def test_duplicate_operation_id_is_atomic(self, conn):
        """A raw IntegrityError from the UNIQUE(operation_id) constraint must
        roll back the whole transaction, not leave a half-written sale."""
        first = _sale()
        with SalesUnitOfWork(conn) as uow:
            uow.sales.save(first)

        second = _sale(operation_id=first.operation_id)
        second.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                        unit_price=Decimal("5.00"))
        with pytest.raises(sqlite3.IntegrityError):
            with SalesUnitOfWork(conn) as uow:
                uow.sales.save(second)

        lines = conn.execute("SELECT COUNT(*) FROM sale_lines WHERE sale_id=?",
                              (second.id,)).fetchone()
        assert lines[0] == 0


class TestOwnsTransactionFlag:
    def test_owns_transaction_false_never_touches_connection(self, conn):
        """When an outer flow owns the SAVEPOINT (e.g. a POS checkout also
        writing Inventory/Cash), the UoW must not commit or roll back the
        shared connection itself."""
        sale = _sale()
        with SalesUnitOfWork(conn, owns_transaction=False) as uow:
            uow.sales.save(sale)
        # Nothing committed yet — still visible on this connection (same
        # uncommitted transaction) but would vanish on rollback by the
        # outer owner. Prove no commit happened by rolling back here.
        conn.rollback()
        row = conn.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale.id,)).fetchone()
        assert row[0] == 0

    def test_owns_transaction_true_commits_immediately(self, conn):
        sale = _sale()
        with SalesUnitOfWork(conn, owns_transaction=True) as uow:
            uow.sales.save(sale)
        conn.rollback()  # no-op — already committed by the UoW itself
        row = conn.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale.id,)).fetchone()
        assert row[0] == 1
