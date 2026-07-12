# tests/test_compras_pro_prov_repo.py
"""Regresión: ModuloComprasPro debe inicializar self._prov_repo.

Bug: varios subtabs (asignar QR, alta directa) usaban self._prov_repo
(get_sucursales_activas / get_activos) pero el atributo nunca se asignaba en
__init__ → AttributeError al cargar sucursales/proveedores (combos vacíos).
"""
import sqlite3

import pytest


def _db_con_datos():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.execute("INSERT INTO sucursales (id,nombre,activa) VALUES ('s1','Centro',1)")
    conn.execute("INSERT INTO proveedores (id,nombre,activo) VALUES ('p1','ACME',1)")
    conn.commit()
    return conn


def test_proveedor_repository_metodos_contra_born_clean():
    from repositories.proveedor_repository import ProveedorRepository
    repo = ProveedorRepository(_db_con_datos())
    sucs = repo.get_sucursales_activas()
    provs = repo.get_activos()
    assert any(s["nombre"] == "Centro" for s in sucs)
    assert any(p["nombre"] == "ACME" for p in provs)


def test_modulo_compras_pro_inicializa_prov_repo():
    pytest.importorskip("PyQt5")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import types
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    container = types.SimpleNamespace(db=_db_con_datos(), sucursal_id="s1")
    from modulos.compras_pro import ModuloComprasPro
    w = ModuloComprasPro(container)
    # El atributo debe existir y ser el repositorio correcto
    from repositories.proveedor_repository import ProveedorRepository
    assert isinstance(w._prov_repo, ProveedorRepository)
    # El combo de sucursal destino (subtab asignar QR) debe poblarse, no quedar vacío
    assert w.qr_sucursal_destino.count() >= 1
