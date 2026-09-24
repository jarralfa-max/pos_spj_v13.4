"""Migración 263 — los proveedores heredados entran al maestro canónico.

Lo que más podía salir mal en esta migración NO es que falle: es que funcione a
medias sin avisar. Tres formas concretas, y una prueba para cada una:

1. que cambie el id, dejando sin proveedor a todas las compras ya registradas;
2. que pierda los bloqueos, habilitando para comprar a quien estaba bloqueado;
3. que al reejecutarse duplique o pise lo capturado después del corte.
"""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.repositories.suppliers.base import normalize_name
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
from backend.shared.ids import new_uuid

_263 = importlib.import_module("migrations.standalone.263_suppliers_legacy_into_master")


def _legacy(conn, *, con_bloqueos: bool = True):
    columnas = ("id TEXT PRIMARY KEY, nombre TEXT, rfc TEXT, activo INTEGER,"
                " fecha_alta TEXT")
    if con_bloqueos:
        columnas += ", compras_habilitadas INTEGER, bloqueado_financiero INTEGER"
    conn.execute(f"CREATE TABLE proveedores ({columnas})")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_supplier_schema(c)
    c.commit()
    yield c
    c.close()


def _maestro(conn) -> dict:
    return {r["id"]: r for r in conn.execute("SELECT * FROM supplier_master")}


def _bloqueos(conn, supplier_id) -> set[str]:
    return {r["block_type"] for r in conn.execute(
        "SELECT block_type FROM supplier_blocks WHERE supplier_id=? AND active=1",
        (supplier_id,))}


class TestTheCutover:
    def test_the_id_is_preserved_so_existing_purchases_still_resolve(self, conn):
        """EL RIESGO Nº1. `purchase_orders.supplier_id` y compañía apuntan a este
        id; cambiarlo dejaría todos esos documentos sin proveedor resoluble."""
        _legacy(conn, con_bloqueos=False)
        heredado = new_uuid()
        conn.execute("INSERT INTO proveedores VALUES (?,?,?,?,?)",
                     (heredado, "Abarrotes Viejo SA", "AAA010101AAA", 1,
                      "2024-03-01 10:00:00"))
        conn.commit()
        _263.run(conn)
        assert heredado in _maestro(conn)

    def test_the_name_rfc_and_date_come_across(self, conn):
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Abarrotes Viejo SA',"
                     "'aaa010101aaa',1,'2024-03-01 10:00:00')")
        conn.commit()
        _263.run(conn)
        fila = _maestro(conn)["s1"]
        assert fila["legal_name"] == "Abarrotes Viejo SA"
        assert fila["tax_identifier"] == "AAA010101AAA"   # normalizado a mayúsculas
        assert fila["created_at"] == "2024-03-01 10:00:00"
        assert fila["status"] == "ACTIVE"

    def test_the_normalized_name_matches_what_the_module_would_write(self, conn):
        """Si difiriera, el proveedor migrado no se encontraría por el mismo
        texto que uno capturado en el módulo — una diferencia invisible."""
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Cárnes del Nórte S.A.',"
                     "NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        assert _maestro(conn)["s1"]["normalized_name"] == normalize_name(
            "Cárnes del Nórte S.A.")

    def test_an_inactive_supplier_arrives_inactive_not_rejected(self, conn):
        """Rechazado significa que se evaluó y se descartó; eso nadie lo capturó."""
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','De Baja SA',NULL,0,NULL)")
        conn.commit()
        _263.run(conn)
        assert _maestro(conn)["s1"]["status"] == "INACTIVE"

    def test_codes_continue_the_existing_sequence(self, conn):
        """Si el código chocara, el INSERT fallaría por UNIQUE; y si no
        continuara, el siguiente alta desde la app chocaría con el migrado."""
        conn.execute(
            "INSERT INTO supplier_master (id, supplier_code, legal_name,"
            " normalized_name, status, created_at, updated_at)"
            " VALUES ('ya','PRV-000007','Ya Existente','yaexistente','ACTIVE',"
            " datetime('now'), datetime('now'))")
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Uno',NULL,1,NULL)")
        conn.execute("INSERT INTO proveedores VALUES ('s2','Dos',NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        maestro = _maestro(conn)
        assert {maestro["s1"]["supplier_code"], maestro["s2"]["supplier_code"]} == {
            "PRV-000008", "PRV-000009"}


class TestBlocksAreNotLost:
    def test_a_purchasing_block_becomes_a_purchasing_block_row(self, conn):
        """EL RIESGO Nº2: perder el bloqueo habilita para comprar a quien estaba
        bloqueado, sin que nadie lo decida."""
        _legacy(conn)
        conn.execute("INSERT INTO proveedores VALUES "
                     "('s1','Sin Compras SA',NULL,1,'2024-01-01',0,0)")
        conn.commit()
        _263.run(conn)
        assert _bloqueos(conn, "s1") == {"PURCHASING_BLOCK"}

    def test_a_financial_block_becomes_a_payment_block_row(self, conn):
        _legacy(conn)
        conn.execute("INSERT INTO proveedores VALUES "
                     "('s1','Moroso SA',NULL,1,'2024-01-01',1,1)")
        conn.commit()
        _263.run(conn)
        assert _bloqueos(conn, "s1") == {"PAYMENT_BLOCK"}

    def test_both_blocks_at_once_are_both_preserved(self, conn):
        _legacy(conn)
        conn.execute("INSERT INTO proveedores VALUES "
                     "('s1','Doblemente SA',NULL,1,'2024-01-01',0,1)")
        conn.commit()
        _263.run(conn)
        assert _bloqueos(conn, "s1") == {"PURCHASING_BLOCK", "PAYMENT_BLOCK"}

    def test_an_unblocked_supplier_gets_no_block_invented(self, conn):
        _legacy(conn)
        conn.execute("INSERT INTO proveedores VALUES "
                     "('s1','Normal SA',NULL,1,'2024-01-01',1,0)")
        conn.commit()
        _263.run(conn)
        assert _bloqueos(conn, "s1") == set()

    def test_without_the_178_columns_no_block_is_invented(self, conn):
        """Base anterior a la migración 178: no hay marcas que traducir."""
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Antiguo SA',NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        assert _bloqueos(conn, "s1") == set()


class TestItIsSafeToRerun:
    def test_running_twice_does_not_duplicate(self, conn):
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Uno',NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        _263.run(conn)
        assert len(_maestro(conn)) == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_blocks").fetchone()[0] == 0

    def test_it_never_overwrites_what_was_captured_afterwards(self, conn):
        """Si alguien edita el proveedor en el módulo después del corte, volver a
        correr la migración no puede devolverle el nombre viejo."""
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','Nombre Viejo',NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        conn.execute("UPDATE supplier_master SET legal_name='Nombre Corregido'"
                     " WHERE id='s1'")
        conn.commit()
        _263.run(conn)
        assert _maestro(conn)["s1"]["legal_name"] == "Nombre Corregido"


class TestItDegradesQuietly:
    def test_a_born_clean_install_has_nothing_to_migrate(self, conn):
        _263.run(conn)  # no existe `proveedores`
        assert _maestro(conn) == {}

    def test_an_empty_legacy_table_is_fine(self, conn):
        _legacy(conn, con_bloqueos=False)
        conn.commit()
        _263.run(conn)
        assert _maestro(conn) == {}

    def test_a_nameless_supplier_is_skipped_not_invented(self, conn):
        """`legal_name` es NOT NULL y un proveedor sin nombre no se puede
        mostrar ni elegir. Se deja fuera; inventarle un nombre sería peor."""
        _legacy(conn, con_bloqueos=False)
        conn.execute("INSERT INTO proveedores VALUES ('s1','',NULL,1,NULL)")
        conn.execute("INSERT INTO proveedores VALUES ('s2','Con Nombre',NULL,1,NULL)")
        conn.commit()
        _263.run(conn)
        assert set(_maestro(conn)) == {"s2"}
