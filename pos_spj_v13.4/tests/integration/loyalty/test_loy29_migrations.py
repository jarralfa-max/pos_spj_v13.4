"""LOY-29 — migraciones 290 (permisos de Fidelidad/Tarjetas) y 291 (tablas legacy).

* 290: el dueño de la instalación tenía 4 de 58 acciones de Fidelidad y 0 de
  27 de Tarjetas, así que el módulo era visible pero inoperable. Ahora
  system_owner y admin reciben todo; gerente el juego operativo; cajero nada
  nuevo. La lista transcrita debe coincidir con los permisos del contexto.
* 291: retira las tablas legacy vacías y CONSERVA las que tengan filas (salvo
  la configuración de fábrica), y es idempotente.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.loyalty.permissions import ALL_LOYALTY_PERMISSIONS
from backend.application.loyalty_cards.permissions import ALL_LOYALTY_CARDS_PERMISSIONS
from backend.shared.ids import new_uuid

_290 = importlib.import_module("migrations.standalone.290_seed_loyalty_role_permissions")
_291 = importlib.import_module("migrations.standalone.291_drop_legacy_loyalty_tables")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT);"
        "CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT, accion TEXT,"
        " permitido INTEGER, UNIQUE(rol_id, modulo, accion));")
    for rol in ("system_owner", "admin", "gerente", "cajero"):
        c.execute("INSERT INTO roles VALUES (?,?)", (new_uuid(), rol))
    c.commit()
    yield c
    c.close()


def _acciones(conn, rol: str, modulo: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT rp.accion FROM rol_permisos rp JOIN roles r ON r.id = rp.rol_id"
        " WHERE r.nombre = ? AND rp.modulo = ?", (rol, modulo))}


class TestSeed290:
    def test_transcription_matches_the_context_permissions(self):
        assert {f"GROWTH_ENGINE.{a}" for a in _290._FIDELIDAD} == ALL_LOYALTY_PERMISSIONS
        assert {f"TARJETAS_FIDELIDAD.{a}" for a in _290._TARJETAS} == ALL_LOYALTY_CARDS_PERMISSIONS

    def test_owner_and_admin_get_everything(self, conn):
        _290.run(conn)
        for rol in ("system_owner", "admin"):
            assert _acciones(conn, rol, "GROWTH_ENGINE") == set(_290._FIDELIDAD)
            assert _acciones(conn, rol, "TARJETAS_FIDELIDAD") == set(_290._TARJETAS)

    def test_manager_operates_but_does_not_define_or_approve(self, conn):
        _290.run(conn)
        gerente = _acciones(conn, "gerente", "GROWTH_ENGINE")
        assert {"puntos.acreditar", "cupon.emitir", "membresia.inscribir"} <= gerente
        assert not {"programa.aprobar", "campana.activar", "sorteo.sortear",
                    "configuracion.editar"} & gerente
        tarjetas = _acciones(conn, "gerente", "TARJETAS_FIDELIDAD")
        assert {"tarjeta.crear", "tarjeta.reponer", "reimprimir"} <= tarjetas
        assert not {"plantilla.aprobar", "lote.aprobar", "qr.rotar"} & tarjetas

    def test_cashier_gets_nothing_new_and_seed_is_idempotent(self, conn):
        _290.run(conn)
        antes = conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0]
        _290.run(conn)
        assert conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0] == antes
        assert not _acciones(conn, "cajero", "GROWTH_ENGINE")
        assert not _acciones(conn, "cajero", "TARJETAS_FIDELIDAD")


class TestDropLegacy291:
    def test_drops_empty_keeps_populated_and_factory_config_goes(self):
        c = sqlite3.connect(":memory:")
        c.executescript(
            "CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, puntos INTEGER);"
            "CREATE TABLE raffles (id TEXT PRIMARY KEY);"
            "CREATE TABLE tarjetas_fidelidad (id TEXT PRIMARY KEY);"
            "INSERT INTO tarjetas_fidelidad VALUES ('con-historia');"
            "CREATE TABLE config_programa_fidelidad (id TEXT PRIMARY KEY, puntos_por_peso REAL);"
            "INSERT INTO config_programa_fidelidad VALUES ('1', 1.0);"
            "CREATE TABLE loyalty_transactions (id TEXT PRIMARY KEY);")
        _291.run(c)
        tablas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "loyalty_ledger" not in tablas
        assert "raffles" not in tablas
        assert "config_programa_fidelidad" not in tablas
        assert "tarjetas_fidelidad" in tablas  # tiene historia: se conserva
        assert "loyalty_transactions" in tablas  # canónica: jamás se toca
        _291.run(c)  # idempotente

    def test_never_lists_a_canonical_table(self):
        from backend.infrastructure.db.schema.commercial_instruments_schema import (
            COMMERCIAL_INSTRUMENTS_TABLES,
        )
        from backend.infrastructure.db.schema.loyalty_cards_schema import LOYALTY_CARDS_TABLES
        from backend.infrastructure.db.schema.loyalty_schema import LOYALTY_TABLES
        from backend.infrastructure.db.schema.sweepstakes_schema import SWEEPSTAKES_TABLES

        canonicas = (set(LOYALTY_TABLES) | set(COMMERCIAL_INSTRUMENTS_TABLES)
                     | set(SWEEPSTAKES_TABLES) | set(LOYALTY_CARDS_TABLES))
        assert not canonicas & set(_291.LEGACY_LOYALTY_TABLES)
