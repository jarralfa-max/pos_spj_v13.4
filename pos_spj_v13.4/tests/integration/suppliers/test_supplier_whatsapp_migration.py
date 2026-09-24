"""Migración 261 — `supplier_contacts.whatsapp_e164`, sus DOS patas.

El esquema de Proveedores es DDL de creación pura: `_DDL` + `_INDEXES` aplicados
por `create_supplier_schema()`, todo `CREATE TABLE IF NOT EXISTS`, sin ningún
mecanismo de columna guardada. Por eso la columna necesita dos caminos y aquí se
prueban los dos:

    instalación NUEVA      → la trae `create_supplier_schema()`
    instalación EXISTENTE  → la añade la migración 261

Probar sólo uno dejaría la mitad de las instalaciones sin el campo, y el síntoma
sería un contacto cuyo WhatsApp se teclea y no se guarda.
"""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema

_migracion = importlib.import_module(
    "migrations.standalone.261_supplier_contact_whatsapp")


def _columnas(conn, tabla: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _tabla_antigua(conn) -> None:
    """`supplier_contacts` tal como existía ANTES de la columna."""
    conn.execute(
        """
        CREATE TABLE supplier_contacts (
            id TEXT NOT NULL PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            name TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            phone_e164 TEXT,
            email TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            receives_purchase_orders INTEGER NOT NULL DEFAULT 0,
            receives_payment_receipts INTEGER NOT NULL DEFAULT 0,
            receives_notifications INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
        """)
    conn.commit()


# ── pata 1: instalaciones nuevas ────────────────────────────────────────────
def test_una_instalacion_nueva_ya_trae_la_columna(conn):
    create_supplier_schema(conn)
    assert "whatsapp_e164" in _columnas(conn, "supplier_contacts")


def test_en_una_instalacion_nueva_la_migracion_no_hace_nada(conn):
    create_supplier_schema(conn)
    antes = _columnas(conn, "supplier_contacts")

    _migracion.run(conn)

    assert _columnas(conn, "supplier_contacts") == antes


# ── pata 2: instalaciones existentes ────────────────────────────────────────
def test_la_migracion_agrega_la_columna_a_una_tabla_antigua(conn):
    _tabla_antigua(conn)
    assert "whatsapp_e164" not in _columnas(conn, "supplier_contacts")

    _migracion.run(conn)

    assert "whatsapp_e164" in _columnas(conn, "supplier_contacts")


def test_es_idempotente(conn):
    """Comprueba `PRAGMA table_info` en vez de envolver en `try/except`, que
    también taparía un error distinto del de 'columna duplicada'."""
    _tabla_antigua(conn)
    _migracion.run(conn)
    _migracion.run(conn)

    assert sorted(_columnas(conn, "supplier_contacts")).count("whatsapp_e164") == 1


def test_conserva_las_filas_existentes(conn):
    """Un `ALTER ADD COLUMN` no debe perder contactos ya capturados."""
    _tabla_antigua(conn)
    conn.execute(
        "INSERT INTO supplier_contacts (id, supplier_id, name, contact_type, phone_e164)"
        " VALUES ('c1', 's1', 'Ana', 'PURCHASING', '+525511112222')")
    conn.commit()

    _migracion.run(conn)

    fila = conn.execute(
        "SELECT name, phone_e164, whatsapp_e164 FROM supplier_contacts").fetchone()
    assert fila["name"] == "Ana"
    assert fila["phone_e164"] == "+525511112222"
    assert fila["whatsapp_e164"] is None


# ── fallar sin romper ───────────────────────────────────────────────────────
def test_sin_la_tabla_no_revienta(conn):
    """Una base sin el contexto de Proveedores no debe tumbar la cadena de
    migraciones: `create_supplier_schema()` ya crearía la columna."""
    _migracion.run(conn)  # no lanza
