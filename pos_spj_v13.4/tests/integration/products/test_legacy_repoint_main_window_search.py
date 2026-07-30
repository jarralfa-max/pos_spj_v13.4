"""PROD corte de legacy (Fase A/B) — búsqueda de la ventana principal canónica.

`MainWindowReadRepository.buscar_productos` compone nombre/código de `products`,
precio de la lista BASE (`product_price`) y existencia = disponible de
`inventory_balances`, en vez de la tabla legacy `productos`.
"""

import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(c)
    c.execute("PRAGMA foreign_keys=OFF")
    return c


def test_buscar_productos_lee_canonico(db):
    from repositories.main_window_repository import MainWindowReadRepository

    pid = new_uuid()
    db.execute(
        "INSERT INTO products (id,code,name,name_normalized,product_type,"
        "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid, "P001", "Pollo entero", "pollo entero", "RESALE_PRODUCT", "ACTIVE", "kg"))
    blid = db.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()["id"]
    db.execute("INSERT INTO product_price (id,price_list_id,product_id,branch_id,"
               "sale_price) VALUES (?,?,?, '', '95')", (new_uuid(), blid, pid))
    db.execute("INSERT INTO inventory_balances (id,product_id,branch_id,warehouse_id,"
               "inventory_status,quantity,reserved_quantity,updated_at) "
               "VALUES (?,?, 'b1','w1','AVAILABLE','10','2', datetime('now'))",
               (new_uuid(), pid))
    db.commit()

    rows = MainWindowReadRepository(db).buscar_productos("Pollo")
    assert len(rows) == 1
    assert rows[0]["nombre"] == "Pollo entero"
    assert rows[0]["precio"] == pytest.approx(95.0)         # de product_price BASE
    assert rows[0]["existencia"] == pytest.approx(8.0)      # 10 − 2 reservado

    # producto inactivo no aparece
    pid2 = new_uuid()
    db.execute(
        "INSERT INTO products (id,code,name,name_normalized,product_type,"
        "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid2, "P002", "Pollo viejo", "pollo viejo", "RESALE_PRODUCT",
         "DISCONTINUED", "kg"))
    db.commit()
    assert [r["nombre"] for r in MainWindowReadRepository(db).buscar_productos("Pollo")] \
        == ["Pollo entero"]
