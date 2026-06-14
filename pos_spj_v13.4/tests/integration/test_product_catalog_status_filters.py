from __future__ import annotations

import sqlite3

import pytest

from backend.application.queries.product_query_service import ProductQueryService


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            codigo TEXT,
            codigo_barras TEXT,
            nombre TEXT,
            categoria TEXT,
            precio REAL,
            existencia REAL,
            activo INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO productos(id, codigo, codigo_barras, nombre, categoria, precio, existencia, activo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "A", "BA", "Activo", "Cat", 10, 5, 1),
            (2, "D", "BD", "Eliminado", "Cat", 20, 0, 0),
        ],
    )
    return conn


@pytest.mark.parametrize("status_filter", ["active", "deleted", "all"])
def test_product_catalog_status_filters_are_semantic_strings(status_filter: str) -> None:
    rows = ProductQueryService.from_connection(_db()).list_catalog_rows(status_filter=status_filter)

    assert isinstance(rows, list)


def test_product_catalog_status_filter_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="status_filter must be one of"):
        ProductQueryService.from_connection(_db()).list_catalog_rows(status_filter="0")
