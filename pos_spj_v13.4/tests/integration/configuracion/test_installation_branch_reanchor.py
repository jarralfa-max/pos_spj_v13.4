"""SDLC-ARQ-TERM-002 — re-anclar la sucursal de la estación.

Contra el esquema born-clean real (`make_db()` + las migraciones que el ítem
necesita), construido una vez por módulo; cada prueba trabaja sobre una copia en
memoria (`sqlite3.Connection.backup`). Nunca se abre un `.db` real.

Paso 1 del plan (T0): fija lo que se conserva y reproduce los defectos tal como
estaban. Los defectos se retiraron al corregirlos: los del caso de uso (sin
permiso, sin auditoría) en el paso 4 —reglas nuevas en
`test_installation_branch_reanchor_use_case.py`— y el fallback silencioso a la
sucursal propia en el paso 5 —`test_station_without_anchor.py`—.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    SqliteInstallationBranchRepository,
)
from backend.shared.ids import new_uuid


# ── base ─────────────────────────────────────────────────────────────────────
#: Además del esquema born-clean: el motor de replicación (pendientes de sincronizar).
_MIGRACIONES = ("350_replication_engine",)


@pytest.fixture(scope="module")
def template():
    import importlib

    from tests.integration._born_clean_db import make_db

    conn = make_db()
    for nombre in _MIGRACIONES:
        importlib.import_module(f"migrations.standalone.{nombre}").run(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def conn(template):
    copia = sqlite3.connect(":memory:")
    template.backup(copia)
    copia.row_factory = sqlite3.Row
    yield copia
    copia.close()


def _sucursal(conn, nombre: str, *, activa: int = 1) -> str:
    bid = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,?)",
                 (bid, nombre, activa))
    conn.commit()
    return bid


def _usuario(conn, rol: str, sucursal: str | None) -> str:
    uid = new_uuid()
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id,"
                 " activo) VALUES (?,?,?,?,?,?,1)",
                 (uid, rol, f"{rol}-{uid[-6:]}", "x", rol, sucursal))
    conn.commit()
    return uid


def _login(user_id: str, rol: str, sucursal: str | None):
    return SimpleNamespace(
        credentials=SimpleNamespace(id=user_id, branch_id=sucursal, role=rol,
                                    full_name=rol, username=rol),
        session=SimpleNamespace(workstation_id="ws-term-002", session_id=new_uuid()),
    )


# ── lo que se conserva ───────────────────────────────────────────────────────
class TestSeConserva:
    def test_the_base_schema_anchors_the_installation(self, conn):
        assert SqliteInstallationBranchRepository(conn).get() is not None

    def test_set_and_get_round_trip(self, conn):
        destino = _sucursal(conn, "Norte")
        repo = SqliteInstallationBranchRepository(conn)
        assert repo.set(destino) == (destino, "Norte")
        assert repo.get() == (destino, "Norte")

    def test_an_unknown_or_inactive_branch_is_rejected(self, conn):
        repo = SqliteInstallationBranchRepository(conn)
        with pytest.raises(ValueError, match="activa"):
            repo.set(new_uuid())
        with pytest.raises(ValueError, match="activa"):
            repo.set(_sucursal(conn, "Cerrada", activa=0))

    def test_the_session_operates_the_anchored_site(self, conn):
        propia = _sucursal(conn, "Propia")
        anclada = SqliteInstallationBranchRepository(conn).get()
        dueno = _usuario(conn, "system_owner", propia)
        ctx = ApplicationContextBuilder(conn).build(_login(dueno, "system_owner", propia))
        assert (ctx.branch_id, ctx.branch_name) == anclada
