"""Resolución del ancla de la estación (reescrita en SDLC-ARQ-TEST-001).

Sustituye a `tests/test_installation_branch_resolution.py`, que importaba
`core.services.branch_resolution` y `repositories.*`, ya borrados. Conserva el
contrato que sigue vigente, sobre el código actual: un valor inválido en
`sucursal_instalacion_id` no es ancla y nunca se inventa la sucursal «Principal»
(evidencia original: `configuraciones.sucursal_instalacion_id = 'None'`).
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    INSTALLATION_BRANCH_KEY,
    SqliteInstallationBranchRepository,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE sucursales (id TEXT, nombre TEXT, activa INTEGER DEFAULT 1);
    """)
    yield c
    c.close()


def _sucursal(conn, nombre: str, *, activa: int = 1, identidad: str | None = "") -> str | None:
    bid = new_uuid() if identidad == "" else identidad
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,?)",
                 (bid, nombre, activa))
    return bid


def _anclar_crudo(conn, valor) -> None:
    conn.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)",
                 (INSTALLATION_BRANCH_KEY, valor))


def test_a_valid_anchor_resolves_to_its_branch(conn):
    cadenas = _sucursal(conn, "Cadenas")
    _anclar_crudo(conn, cadenas)
    assert SqliteInstallationBranchRepository(conn).get() == (cadenas, "Cadenas")


@pytest.mark.parametrize("valor", ["None", "null", "", "0", None, "no-existe"])
def test_an_invalid_value_is_no_anchor(conn, valor):
    """Ni siquiera con una «Principal» disponible: no se adivina."""
    _sucursal(conn, "Principal")
    _sucursal(conn, "Sin identidad", identidad=None)
    _anclar_crudo(conn, valor)
    assert SqliteInstallationBranchRepository(conn).get() is None


def test_a_missing_key_is_no_anchor(conn):
    _sucursal(conn, "Principal")
    assert SqliteInstallationBranchRepository(conn).get() is None


def test_setting_refuses_a_branch_that_does_not_exist(conn):
    with pytest.raises(ValueError):
        SqliteInstallationBranchRepository(conn).set(new_uuid())
    assert conn.execute("SELECT COUNT(*) FROM configuraciones").fetchone()[0] == 0


def test_setting_refuses_an_inactive_branch(conn):
    cerrada = _sucursal(conn, "Cerrada", activa=0)
    with pytest.raises(ValueError):
        SqliteInstallationBranchRepository(conn).set(cerrada)
    assert conn.execute("SELECT COUNT(*) FROM configuraciones").fetchone()[0] == 0


def test_setting_stores_the_identity_not_a_string_of_none(conn):
    cadenas = _sucursal(conn, "Cadenas")
    assert SqliteInstallationBranchRepository(conn).set(cadenas) == (cadenas, "Cadenas")
    guardado = conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                            (INSTALLATION_BRANCH_KEY,)).fetchone()[0]
    assert guardado == cadenas
