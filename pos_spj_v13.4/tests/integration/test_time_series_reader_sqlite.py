"""BI-8 — SqliteDailyProductSalesReader against a real (minimal) SQLite schema.

Builds just the two tables the reader touches directly rather than going
through the full migration engine — the shared `fresh_db()`/`make_db()`
helpers currently have a pre-existing, unrelated bootstrap failure (see
docs/refactor/BI-4_query_layer.md and [[env_nested_git_repo_pos_spj]] gotcha
4/BI-4 finding), and this reader only ever touches `ventas`/`detalles_venta`.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.infrastructure.db.repositories.forecasting.sqlite_time_series_reader import (
    SqliteDailyProductSalesReader,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("""
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, estado TEXT, fecha TEXT, sucursal_id TEXT
        )
    """)
    c.execute("""
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL
        )
    """)
    yield c
    c.close()


def _sale(conn, *, product_id, branch_id, day, cantidad, estado="completada"):
    sale_id = new_uuid()
    conn.execute("INSERT INTO ventas (id, estado, fecha, sucursal_id) VALUES (?,?,?,?)",
                 (sale_id, estado, f"{day.isoformat()} 12:00:00", branch_id))
    conn.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (?,?,?,?)",
        (new_uuid(), sale_id, product_id, cantidad))
    conn.commit()


def test_rejects_wrong_series_key(conn):
    reader = SqliteDailyProductSalesReader(conn)
    with pytest.raises(ValueError):
        reader.read_observations("some_other_series", {"product": "p1"},
                                  date(2026, 8, 1), date(2026, 8, 2))


def test_requires_product_dimension(conn):
    reader = SqliteDailyProductSalesReader(conn)
    with pytest.raises(ValueError):
        reader.read_observations("daily_sales_by_product", {}, date(2026, 8, 1), date(2026, 8, 2))


def test_real_sale_day_is_not_imputed(conn):
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=5)
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1"},
                                    date(2026, 8, 1), date(2026, 8, 1))
    assert len(obs) == 1
    assert obs[0].value == Decimal("5")
    assert obs[0].is_imputed is False


def test_gap_day_is_imputed_zero_with_reason(conn):
    """§18: a day with no sales row must never come back as a bare zero
    indistinguishable from a real zero-sales day."""
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=5)
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1"},
                                    date(2026, 8, 1), date(2026, 8, 3))
    assert [o.timestamp for o in obs] == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]
    assert obs[0].is_imputed is False
    assert obs[1].is_imputed is True
    assert obs[1].imputation_reason == "no_sales_recorded"
    assert obs[1].value == Decimal("0")
    assert obs[2].is_imputed is True


def test_multiple_sales_same_day_are_summed(conn):
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=3)
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=2)
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1"},
                                    date(2026, 8, 1), date(2026, 8, 1))
    assert obs[0].value == Decimal("5")


def test_branch_filter_excludes_other_branches(conn):
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=5)
    _sale(conn, product_id="p1", branch_id="b2", day=date(2026, 8, 1), cantidad=7)
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1", "branch": "b1"},
                                    date(2026, 8, 1), date(2026, 8, 1))
    assert obs[0].value == Decimal("5")


def test_non_completed_sales_are_excluded(conn):
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=5,
          estado="cancelada")
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1"},
                                    date(2026, 8, 1), date(2026, 8, 1))
    assert obs[0].value == Decimal("0")
    assert obs[0].is_imputed is True


def test_other_products_are_excluded(conn):
    _sale(conn, product_id="p1", branch_id="b1", day=date(2026, 8, 1), cantidad=5)
    _sale(conn, product_id="p2", branch_id="b1", day=date(2026, 8, 1), cantidad=9)
    reader = SqliteDailyProductSalesReader(conn)
    obs = reader.read_observations("daily_sales_by_product", {"product": "p1"},
                                    date(2026, 8, 1), date(2026, 8, 1))
    assert obs[0].value == Decimal("5")
