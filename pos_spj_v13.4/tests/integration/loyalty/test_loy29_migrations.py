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


class TestTokenHash292:
    """§32: el token del QR deja de guardarse en claro."""

    _292 = importlib.import_module("migrations.standalone.292_loyalty_card_token_hash")

    def _old_shape(self):
        from backend.infrastructure.db.schema.loyalty_cards_schema import (
            create_loyalty_cards_schema,
        )

        c = sqlite3.connect(":memory:")
        create_loyalty_cards_schema(c)
        c.executescript(
            "DROP TABLE loyalty_card_tokens; DROP TABLE loyalty_digital_card_projections;"
            "DROP TABLE loyalty_card_secrets;"
            "INSERT INTO loyalty_cards (id, card_number, card_type, customer_id, membership_id,"
            " status, issued_at, created_at, updated_at)"
            " VALUES ('c1','LC-1','PHYSICAL','cu','m1','ACTIVE','x','x','x');"
            "CREATE TABLE loyalty_card_tokens (id TEXT PRIMARY KEY, card_id TEXT, token TEXT UNIQUE,"
            " status TEXT, created_at TEXT, rotated_at TEXT, revoked_at TEXT);"
            "INSERT INTO loyalty_card_tokens VALUES ('t1','c1','secreto-en-claro','ACTIVE','x',NULL,NULL);"
            "CREATE TABLE loyalty_digital_card_projections (id TEXT PRIMARY KEY, card_id TEXT UNIQUE,"
            " customer_id TEXT, card_number TEXT, qr_token TEXT, display_fields_json TEXT,"
            " last_refreshed_at TEXT, created_at TEXT);"
            "INSERT INTO loyalty_digital_card_projections VALUES"
            " ('p1','c1','cu','LC-1','secreto-en-claro','{}','x','x');")
        return c

    def test_old_tokens_become_hashes_that_still_resolve(self):
        import hashlib

        c = self._old_shape()
        self._292.run(c)
        columnas = {f[1] for f in c.execute("PRAGMA table_info(loyalty_card_tokens)")}
        assert "token" not in columnas and {"token_hash", "token_prefix", "token_version"} <= columnas
        fila = c.execute("SELECT token_hash, token_version FROM loyalty_card_tokens").fetchone()
        assert fila == (hashlib.sha256(b"secreto-en-claro").hexdigest(), 0)
        volcado = " ".join(str(f) for t in ("loyalty_card_tokens", "loyalty_digital_card_projections")
                           for f in c.execute(f"SELECT * FROM {t}"))
        assert "secreto-en-claro" not in volcado
        assert c.execute("SELECT token_id FROM loyalty_digital_card_projections").fetchone()[0] == "t1"
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='loyalty_card_secrets'").fetchone()
        self._292.run(c)  # idempotente

    def test_an_unrelated_broken_view_does_not_block_the_rebuild(self):
        """La base real trae una vista legacy rota; renombrar en modo moderno la
        revalidaba y tumbaba el arranque completo."""
        c = self._old_shape()
        c.execute("PRAGMA legacy_alter_table=ON")
        c.execute("CREATE TABLE tabla_que_se_va (x)")
        c.execute("CREATE VIEW v_rota AS SELECT x FROM tabla_que_se_va")
        c.execute("DROP TABLE tabla_que_se_va")
        c.execute("PRAGMA legacy_alter_table=OFF")
        self._292.run(c)
        assert "token_hash" in {f[1] for f in c.execute("PRAGMA table_info(loyalty_card_tokens)")}


class TestPreprinted293:
    _293 = importlib.import_module("migrations.standalone.293_loyalty_card_preprinted_assignment")

    def test_cards_accept_unassigned_rows_and_children_survive(self):
        from backend.infrastructure.db.schema.loyalty_cards_schema import (
            create_loyalty_cards_schema,
        )

        c = sqlite3.connect(":memory:")
        c.execute("PRAGMA foreign_keys=ON")
        create_loyalty_cards_schema(c)
        c.executescript(
            "DROP TABLE loyalty_card_assignments; DROP TABLE loyalty_card_tokens;"
            "DROP TABLE loyalty_cards;"
            "CREATE TABLE loyalty_cards (id TEXT NOT NULL PRIMARY KEY, card_number TEXT NOT NULL"
            " UNIQUE, card_type TEXT NOT NULL, customer_id TEXT NOT NULL, membership_id TEXT NOT"
            " NULL, status TEXT NOT NULL DEFAULT 'ISSUED', issued_at TEXT NOT NULL, activated_at"
            " TEXT, blocked_at TEXT, block_reason TEXT, replaces_card_id TEXT, replaced_by_card_id"
            " TEXT, cancelled_at TEXT, cancel_reason TEXT, expires_at TEXT, created_at TEXT NOT"
            " NULL, updated_at TEXT NOT NULL);"
            "INSERT INTO loyalty_cards (id, card_number, card_type, customer_id, membership_id,"
            " issued_at, created_at, updated_at) VALUES ('c1','LC-1','PHYSICAL','cu','m1','x','x','x');")
        create_loyalty_cards_schema(c)  # recrea tokens con FK a loyalty_cards
        c.execute("INSERT INTO loyalty_card_tokens (id, card_id, token_hash, token_prefix,"
                  " status, created_at) VALUES ('t1','c1',?, 'abcdef', 'ACTIVE', 'x')", ("a" * 64,))
        c.commit()
        self._293.run(c)
        nulos = {f[1]: f[3] for f in c.execute("PRAGMA table_info(loyalty_cards)")}
        assert nulos["customer_id"] == 0 and nulos["membership_id"] == 0
        assert c.execute("SELECT COUNT(*) FROM loyalty_card_tokens").fetchone()[0] == 1
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        c.execute("INSERT INTO loyalty_cards (id, card_number, card_type, status, issued_at,"
                  " created_at, updated_at) VALUES ('c2','LC-2','PHYSICAL','UNASSIGNED','x','x','x')")
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='loyalty_card_assignments'").fetchone()
        self._293.run(c)  # idempotente
