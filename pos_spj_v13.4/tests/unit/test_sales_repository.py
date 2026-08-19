"""SALES-5/POS-5 — SaleRepository round-trip. Mirrors
tests/unit/transfers/test_transfer_write_repository.py's style (pytest,
real sqlite3 :memory: + schema module, small domain-object factory helper)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    c.commit()
    yield c
    c.close()


def _sale(**overrides) -> Sale:
    defaults = dict(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
    defaults.update(overrides)
    return Sale.start(**defaults)


class TestSaveAndGet:
    def test_round_trips_empty_draft_sale(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()

        repo.save(sale)
        conn.commit()

        loaded = repo.get(sale.id)
        assert loaded is not None
        assert loaded.id == sale.id
        assert loaded.status is SaleStatus.DRAFT
        assert loaded.totals.total == Decimal("0")
        assert loaded.lines == []

    def test_round_trips_header_and_lines(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        sale.add_line(
            product_id=new_uuid(), quantity=Quantity(Decimal("2"), "PZA"),
            unit_price=Decimal("45.50"),
            product_snapshot={"nombre": "Bistec", "sku": "BST-1"},
        )
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1"), "KG"),
                      unit_price=Decimal("120.00"))

        repo.save(sale)
        conn.commit()

        loaded = repo.get(sale.id)
        assert loaded.status is SaleStatus.ACTIVE
        assert loaded.totals.total == sale.totals.total == Decimal("211.00")
        assert len(loaded.lines) == 2
        first = next(line for line in loaded.lines if line.product_snapshot.get("sku") == "BST-1")
        assert first.quantity.value == Decimal("2")
        assert first.quantity.unit == "PZA"
        assert first.unit_price == Decimal("45.50")
        assert first.product_snapshot["nombre"] == "Bistec"

    def test_save_replaces_lines_wholesale(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        line = sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                              unit_price=Decimal("10.00"))
        repo.save(sale)
        conn.commit()

        sale.remove_line(line.id)
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("3")),
                      unit_price=Decimal("5.00"))
        repo.save(sale)
        conn.commit()

        loaded = repo.get(sale.id)
        assert len(loaded.lines) == 1
        assert loaded.totals.total == Decimal("15.00")

    def test_save_is_idempotent_upsert_on_id(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        repo.save(sale)
        sale.assign_customer(new_uuid())
        repo.save(sale)  # second save, same id — must update, not duplicate
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        assert count == 1
        assert repo.get(sale.id).customer_id == sale.customer_id

    def test_missing_sale_returns_none(self, conn):
        repo = SaleRepository(conn)
        assert repo.get(new_uuid()) is None

    def test_preserves_discount_and_tax_on_lines(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        line = sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                              unit_price=Decimal("100.00"))
        sale.apply_line_discount(line.id, Decimal("10.00"), authorized=True)
        line.apply_tax(Decimal("16.00"))  # no Sale-level pass-through yet (SALES-3 gap)
        repo.save(sale)
        conn.commit()

        loaded = repo.get(sale.id)
        loaded_line = loaded.lines[0]
        assert loaded_line.discount_total == Decimal("10.00")
        assert loaded_line.tax_total == Decimal("16.00")
        assert loaded_line.line_total == Decimal("106.00")

    def test_no_real_float_reaches_sqlite_columns(self, conn):
        """Guards against a regression where a caller passes float instead of
        Decimal — dec_str() must raise, not silently truncate."""
        from backend.infrastructure.db.repositories.sales.base import dec_str

        with pytest.raises(ValueError):
            dec_str(1.5)


class TestOperationIdempotency:
    def test_operation_exists(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        assert repo.operation_exists(sale.operation_id) is False
        repo.save(sale)
        conn.commit()
        assert repo.operation_exists(sale.operation_id) is True

    def test_get_by_operation_id(self, conn):
        repo = SaleRepository(conn)
        sale = _sale()
        repo.save(sale)
        conn.commit()

        loaded = repo.get_by_operation_id(sale.operation_id)
        assert loaded is not None
        assert loaded.id == sale.id

    def test_duplicate_operation_id_violates_unique_constraint(self, conn):
        repo = SaleRepository(conn)
        first = _sale()
        second = _sale(operation_id=first.operation_id)
        repo.save(first)
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(second)
