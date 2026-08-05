"""P2 repoint — ProductoRepository.has_movements reads the canonical ledger.

The product deletion probe "does this product have inventory movements?" now
consults the canonical ``inventory_ledger_lines`` instead of the legacy
``movimientos_inventario`` table, removing repositories/productos.py from the
legacy-inventory-table consumer set (one fewer DROP blocker).
"""

import sqlite3

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid
from repositories.productos import ProductoRepository


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    return c


def test_has_movements_false_without_ledger_lines():
    conn = _conn()
    assert ProductoRepository(conn).has_movements("p1") is False


def test_has_movements_true_from_canonical_ledger_line():
    conn = _conn()
    conn.execute(
        "INSERT INTO inventory_ledger_lines (id, movement_id, product_id)"
        " VALUES (?,?,?)", (new_uuid(), new_uuid(), "p1"))
    conn.commit()
    repo = ProductoRepository(conn)
    assert repo.has_movements("p1") is True
    assert repo.has_movements("p2") is False  # scoped to the product
