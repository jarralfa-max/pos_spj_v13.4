"""Remediación F — main_window delega su SQL a MainWindowReadRepository.

Caracteriza las lecturas del shell extraídas de interfaz/main_window.py:
nombre de sucursal, vínculo usuario→empleado y la búsqueda global (productos,
clientes, ventas por folio).
"""
import sqlite3

import pytest

from backend.shared.ids import new_uuid
from repositories.main_window_repository import MainWindowReadRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def test_nombre_sucursal(db):
    sid = new_uuid()
    db.execute("INSERT INTO sucursales (id,nombre,activa) VALUES (?,?,1)", (sid, "Centro"))
    db.commit()
    repo = MainWindowReadRepository(db)
    assert repo.nombre_sucursal(sid) == "Centro"
    assert repo.nombre_sucursal(new_uuid()) == ""     # inexistente → ""


def test_personal_id_de_usuario_ambas_rutas(db):
    # Ruta legacy: personal.usuario_id
    u1, p1 = new_uuid(), new_uuid()
    db.execute("INSERT INTO personal (id,nombre,activo,usuario_id) VALUES (?,?,1,?)",
               (p1, "Ana", u1))
    # Ruta canónica: usuarios.personal_id
    u2, p2 = new_uuid(), new_uuid()
    db.execute("INSERT INTO personal (id,nombre,activo) VALUES (?,?,1)", (p2, "Luis"))
    db.execute("INSERT INTO usuarios (id,nombre,usuario,password_hash,personal_id) "
               "VALUES (?,?,?,?,?)", (u2, "Luis", "luis", "x", p2))
    db.commit()
    repo = MainWindowReadRepository(db)
    assert repo.personal_id_de_usuario(u1) == p1
    assert repo.personal_id_de_usuario(u2) == p2
    assert repo.personal_id_de_usuario(new_uuid()) is None


def test_busqueda_global(db):
    pid = new_uuid()
    db.execute("INSERT INTO productos (id,nombre,codigo,precio,existencia,activo) "
               "VALUES (?,?,?,?,?,1)", (pid, "Pollo entero", "P001", 95.0, 10))
    db.execute("INSERT INTO clientes (id,nombre,apellido,telefono,activo) "
               "VALUES (?,?,?,?,1)", (new_uuid(), "Mariana", "Ruiz", "555"))
    db.execute("INSERT INTO ventas (id,folio,total,estado,fecha,usuario) "
               "VALUES (?,?,?,?,datetime('now'),?)", (new_uuid(), "F-777", 200.0, "completada", "u"))
    db.commit()
    repo = MainWindowReadRepository(db)
    assert any(r[0] == "Pollo entero" for r in repo.buscar_productos("Pollo"))
    assert any(r[0] == "Mariana" for r in repo.buscar_clientes("Mari"))
    assert any(r[0] == "F-777" for r in repo.buscar_ventas_por_folio("777"))


def test_busquedas_degradan_sin_excepcion():
    """Sin esquema, las búsquedas devuelven [] en vez de lanzar."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    repo = MainWindowReadRepository(conn)
    assert repo.buscar_productos("x") == []
    assert repo.buscar_clientes("x") == []
    assert repo.buscar_ventas_por_folio("x") == []
    assert repo.nombre_sucursal("x") == ""
    assert repo.personal_id_de_usuario("x") is None
