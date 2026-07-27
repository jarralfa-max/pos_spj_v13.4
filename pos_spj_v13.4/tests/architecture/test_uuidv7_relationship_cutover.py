"""FASE 1 — guard rails for the legacy relationship UUIDv7 cutover.

Validates the canonical parent mapping for the four legacy references being
folded into the cut (turno_id, tarjeta_id, order_id, ticket_id) and proves the
cutover engine produces a referentially-sound UUIDv7 schema (PRAGMA
foreign_key_check passes) on a synthetic copy of those relationships.

The destructive migration (200) is allowed to stay gated/skeleton; this test
enforces that the generated spec documents the correct relationships.
"""

from __future__ import annotations

import importlib
import sqlite3
import uuid

import pytest

from backend.infrastructure.db.uuid_cutover import TableSpec, UuidCutover


# ── canonical relationship map (domain-confirmed) ──────────────────────────────
CANONICAL = {
    ("ventas", "turno_id"): "turnos_caja",
    ("cierres_caja", "turno_id"): "turnos_caja",
    ("movimientos_caja", "turno_id"): "turnos_caja",
    ("card_assignment_history", "tarjeta_id"): "tarjetas_fidelidad",
    ("delivery_cut_items", "order_id"): "delivery_orders",
    ("delivery_cut_items", "cut_id"): "delivery_driver_cuts",
    ("growth_ledger", "ticket_id"): "ventas",
}


def _specs():
    mod = importlib.import_module("migrations.standalone._cutover_spec_generated")
    return {s.name: s for s in mod.CUTOVER_SPECS}


def test_generated_spec_documents_canonical_relationships():
    specs = _specs()
    for (table, col), parent in CANONICAL.items():
        assert table in specs, f"{table} missing from CUTOVER_SPECS"
        assert specs[table].fks.get(col) == parent, (
            f"{table}.{col} must map to {parent}, got {specs[table].fks.get(col)}"
        )


def test_card_assignment_does_not_reference_card_batches():
    specs = _specs()
    assert specs["card_assignment_history"].fks.get("tarjeta_id") != "card_batches"


def test_no_turnos_table_created():
    specs = _specs()
    assert "turnos" not in specs, "no debe existir la tabla 'turnos'; el padre es turnos_caja"
    assert "turnos_caja" in specs


def test_ticket_id_parent_is_ventas_not_legacy_tickets():
    specs = _specs()
    assert specs["growth_ledger"].fks.get("ticket_id") == "ventas"


# ── end-to-end: the cut yields a referentially-sound UUID schema ───────────────
def _synthetic_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
        CREATE TABLE turnos_caja (id INTEGER PRIMARY KEY AUTOINCREMENT, branch_id INTEGER, status TEXT);
        CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT);
        CREATE TABLE delivery_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT);
        CREATE TABLE delivery_driver_cuts (id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER);
        CREATE TABLE ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, turno_id INTEGER, sucursal_id INTEGER);
        CREATE TABLE cierres_caja (id INTEGER PRIMARY KEY AUTOINCREMENT, turno_id INTEGER);
        CREATE TABLE movimientos_caja (id INTEGER PRIMARY KEY AUTOINCREMENT, turno_id INTEGER, venta_id INTEGER);
        CREATE TABLE card_assignment_history (id INTEGER PRIMARY KEY AUTOINCREMENT, tarjeta_id INTEGER);
        CREATE TABLE delivery_cut_items (id INTEGER PRIMARY KEY AUTOINCREMENT, cut_id INTEGER, order_id INTEGER);
        CREATE TABLE growth_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER);

        INSERT INTO sucursales (id, nombre) VALUES (1,'Centro');
        INSERT INTO turnos_caja (id, branch_id, status) VALUES (1,1,'open');
        INSERT INTO tarjetas_fidelidad (id, numero) VALUES (1,'T-1');
        INSERT INTO delivery_orders (id, folio) VALUES (1,'D-1');
        INSERT INTO delivery_driver_cuts (id, driver_id) VALUES (1,1);
        INSERT INTO ventas (id, turno_id, sucursal_id) VALUES (1,1,1);
        INSERT INTO cierres_caja (id, turno_id) VALUES (1,1);
        INSERT INTO movimientos_caja (id, turno_id, venta_id) VALUES (1,1,1);
        INSERT INTO card_assignment_history (id, tarjeta_id) VALUES (1,1);
        INSERT INTO delivery_cut_items (id, cut_id, order_id) VALUES (1,1,1);
        INSERT INTO growth_ledger (id, ticket_id) VALUES (1,1);
        """
    )
    conn.commit()
    return conn


_SYNTH_SPECS = [
    TableSpec("sucursales"),
    TableSpec("turnos_caja", fks={"branch_id": "sucursales"}),
    TableSpec("tarjetas_fidelidad"),
    TableSpec("delivery_orders"),
    TableSpec("delivery_driver_cuts"),
    TableSpec("ventas", fks={"turno_id": "turnos_caja", "sucursal_id": "sucursales"}),
    TableSpec("cierres_caja", fks={"turno_id": "turnos_caja"}),
    TableSpec("movimientos_caja", fks={"turno_id": "turnos_caja", "venta_id": "ventas"}),
    TableSpec("card_assignment_history", fks={"tarjeta_id": "tarjetas_fidelidad"}),
    TableSpec("delivery_cut_items", fks={"cut_id": "delivery_driver_cuts", "order_id": "delivery_orders"}),
    TableSpec("growth_ledger", fks={"ticket_id": "ventas"}),
]


def _is_uuid7(v):
    p = uuid.UUID(str(v))
    return p.version == 7


def test_relationship_cutover_yields_uuid_fks_and_fk_check_passes():
    conn = _synthetic_db()
    UuidCutover(conn, _SYNTH_SPECS).run()
    # the legacy int FKs are now UUIDv7 and resolve to the right parent
    for table, col in (("ventas", "turno_id"), ("cierres_caja", "turno_id"),
                       ("movimientos_caja", "turno_id"),
                       ("card_assignment_history", "tarjeta_id"),
                       ("delivery_cut_items", "order_id"), ("growth_ledger", "ticket_id")):
        val = conn.execute(f"SELECT {col} FROM {table} LIMIT 1").fetchone()[0]
        assert _is_uuid7(val), f"{table}.{col} is not UUIDv7 after cut: {val}"
    # FK check (the engine runs it internally; assert here too for the synthetic schema)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_report_orphans_flags_broken_reference():
    conn = _synthetic_db()
    conn.execute("INSERT INTO ventas (id, turno_id, sucursal_id) VALUES (99, 555, 1)")  # orphan turno
    conn.commit()
    orphans = UuidCutover(conn, _SYNTH_SPECS).report_orphans()
    assert "ventas.turno_id->turnos_caja" in orphans
    assert any(r[1] == 555 for r in orphans["ventas.turno_id->turnos_caja"])
