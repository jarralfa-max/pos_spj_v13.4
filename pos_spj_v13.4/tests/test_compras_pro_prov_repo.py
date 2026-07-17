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


# PUR-13: el test de inicialización de `self._prov_repo` en el monolito
# ModuloComprasPro se retiró — compras_pro.py es ahora un wrapper canónico y la
# asignación/proveedores del contenedor QR viven en el módulo enterprise
# (AssignQrContainerUseCase + SupplierPickerQueryService), cubiertos por sus
# propios tests. El repositorio canónico se valida arriba contra el esquema
# born-clean.
