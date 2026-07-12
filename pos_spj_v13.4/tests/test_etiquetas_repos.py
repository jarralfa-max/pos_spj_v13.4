# tests/test_etiquetas_repos.py
"""Remediación F — etiquetas delega su SQL a repos/servicios.

Caracteriza las lecturas extraídas de modulos/etiquetas.py: catálogo de productos
(ProductoRepository.listar_para_etiquetas), nombre de empresa (ConfigService) y
config de impresora de etiquetas (HardwareConfigRepository).
"""
import json
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


def test_listar_para_etiquetas(db):
    from repositories.productos import ProductoRepository
    db.execute("INSERT INTO productos (id,nombre,precio,unidad,activo) VALUES (?,?,?,?,1)",
               (new_uuid(), "Pollo", 95.0, "kg"))
    db.execute("INSERT INTO productos (id,nombre,precio,unidad,activo) VALUES (?,?,?,?,0)",
               (new_uuid(), "Inactivo", 1.0, "pz"))
    db.commit()
    rows = ProductoRepository(db).listar_para_etiquetas()
    assert len(rows) == 1                       # sólo activos
    assert rows[0][1] == "Pollo"
    assert float(rows[0][2]) == 95.0 and str(rows[0][3]) == "kg"


def test_config_service_nombre_empresa(db):
    from repositories.config_repository import ConfigRepository
    from core.services.config_service import ConfigService
    svc = ConfigService(ConfigRepository(db))
    assert (svc.get("nombre_empresa") or "SPJ") == "SPJ"
    svc.set("nombre_empresa", "Juanis")
    assert svc.get("nombre_empresa") == "Juanis"


def test_hardware_config_repo_etiquetas(db):
    from core.repositories.hardware_config_repository import HardwareConfigRepository
    repo = HardwareConfigRepository(db)
    repo.ensure_schema()
    repo.save_config("etiquetas", "Zebra", {"tipo": "red", "ip": "192.168.1.50"})
    cfg = repo.get_config("etiquetas")
    assert cfg.get("ip") == "192.168.1.50"
    # clave inexistente → {}
    assert repo.get_config("impresora_etiquetas") == {}
