"""Remediación F — planeacion_compras delega su SQL a repositorios.

Caracteriza las dos lecturas extraídas de modulos/planeacion_compras.py:
  · ProductoRepository.listar_activos_combo   (combo de productos activos)
  · PurchaseRepository.ultimo_costo_unitario   (hint de costo de compra)
"""
import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def test_listar_activos_combo(db):
    from repositories.productos import ProductoRepository
    db.execute("INSERT INTO productos (id,nombre,activo) VALUES (?,?,1)", (new_uuid(), "Zanahoria"))
    db.execute("INSERT INTO productos (id,nombre,activo) VALUES (?,?,1)", (new_uuid(), "Ajo"))
    db.execute("INSERT INTO productos (id,nombre,activo) VALUES (?,?,0)", (new_uuid(), "Inactivo"))
    db.commit()
    rows = ProductoRepository(db).listar_activos_combo()
    nombres = [r["nombre"] for r in rows]
    assert nombres == ["Ajo", "Zanahoria"]          # activos, orden alfabético
    assert "Inactivo" not in nombres


def test_ultimo_costo_unitario(db):
    from repositories.purchase_repository import PurchaseRepository
    pid = new_uuid()
    db.execute("INSERT INTO productos (id,nombre,activo) VALUES (?,?,1)", (pid, "Pollo"))
    # dos compras: la más reciente debe ganar
    c1, c2 = new_uuid(), new_uuid()
    db.execute("INSERT INTO compras (id,folio,fecha,estado,usuario) VALUES (?,?,?,?,?)",
               (c1, "F1", "2026-01-01", "completada", "sys"))
    db.execute("INSERT INTO compras (id,folio,fecha,estado,usuario) VALUES (?,?,?,?,?)",
               (c2, "F2", "2026-06-01", "completada", "sys"))
    db.execute("INSERT INTO detalles_compra (id,compra_id,producto_id,cantidad,precio_unitario,subtotal) "
               "VALUES (?,?,?,?,?,?)", (new_uuid(), c1, pid, 1, 18.0, 18.0))
    db.execute("INSERT INTO detalles_compra (id,compra_id,producto_id,cantidad,precio_unitario,subtotal) "
               "VALUES (?,?,?,?,?,?)", (new_uuid(), c2, pid, 1, 22.5, 22.5))
    db.commit()
    assert PurchaseRepository(db).ultimo_costo_unitario(pid) == 22.5


def test_ultimo_costo_sin_compras_es_cero(db):
    from repositories.purchase_repository import PurchaseRepository
    assert PurchaseRepository(db).ultimo_costo_unitario(new_uuid()) == 0.0
