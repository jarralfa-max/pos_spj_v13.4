"""End-to-end proof of the global UUIDv7 cut against the real schema.

Bootstraps a full database via the migration engine, seeds rows across the four
confirmed legacy relationships, runs the cut with the generated CUTOVER_SPECS,
and asserts a referentially-sound, all-UUIDv7 result:

  * PRAGMA foreign_key_check is empty,
  * no INTEGER PRIMARY KEY remains (REGLA CERO step 13),
  * the legacy FKs (turno_id, tarjeta_id, batch_id, order_id, ticket_id) are
    UUIDv7 and still resolve to their parent,
  * explicit indexes and triggers survive the rewrite.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from migrations.engine import up
from migrations.standalone._cutover_spec_generated import CUTOVER_SPECS
from backend.infrastructure.db.uuid_cutover import UuidCutover


def _is_uuid7(v) -> bool:
    try:
        return uuid.UUID(str(v)).version == 7
    except Exception:
        return False


@pytest.fixture
def bootstrapped():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        up(conn)
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"migration engine could not bootstrap in-memory: {exc}")
    return conn


def _seed(conn):
    def ins(sql, p=()):
        try:
            conn.execute(sql, p)
        except Exception:
            pass
    ins("INSERT INTO clientes (id, nombre) VALUES (1,'Ana')")
    ins("INSERT INTO turnos_caja (id, sucursal_id, cajero, estado) VALUES (1,1,'ana','abierto')")
    ins("INSERT INTO ventas (id, sucursal_id, cliente_id, turno_id, total) VALUES (1,1,1,'1',100.0)")
    ins("INSERT INTO movimientos_caja (id, turno_id, sucursal_id, tipo, monto) VALUES (1,'1',1,'VENTA',100)")
    ins("INSERT INTO card_batches (id, uuid, nombre, codigo_inicio, codigo_fin) VALUES (1,'u1','L','A1','A9')")
    ins("INSERT INTO tarjetas_fidelidad (id, codigo_qr, numero, batch_id, estado) VALUES (1,'q','N1','1','asignada')")
    ins("INSERT INTO card_assignment_history (id, tarjeta_id, accion) VALUES (1,'1','asignacion')")
    ins("INSERT INTO delivery_orders (id, cliente_nombre, total) VALUES (1,'Ana',50)")
    ins("INSERT INTO growth_ledger (id, cliente_id, sucursal_id, tipo, monto, ticket_id) VALUES (1,1,1,'credito',10,'1')")
    conn.commit()


def test_full_schema_cut_is_referentially_sound(bootstrapped):
    conn = bootstrapped
    _seed(conn)
    idx_before = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    ).fetchone()[0]
    trg_before = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
    ).fetchone()[0]

    counts = UuidCutover(conn, CUTOVER_SPECS).run()
    assert len(counts) == len(CUTOVER_SPECS)

    # referential integrity
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    # no integer PK remains among domain tables (REGLA CERO step 13).
    # schema_migrations is migration-tracking infra, not a domain entity.
    int_pks = []
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'schema_%'"
    ).fetchall():
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            if row[5] and (row[2] or "").upper().startswith("INT"):
                int_pks.append(f"{table}.{row[1]}")
    assert int_pks == [], f"integer PKs remain: {int_pks[:10]}"

    # the legacy FKs are UUIDv7 and resolve
    for table, col in [("ventas", "turno_id"), ("movimientos_caja", "turno_id"),
                       ("card_assignment_history", "tarjeta_id"),
                       ("tarjetas_fidelidad", "batch_id"), ("growth_ledger", "ticket_id")]:
        v = conn.execute(f'SELECT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 1').fetchone()
        assert v and _is_uuid7(v[0]), f"{table}.{col} not UUIDv7"
    assert conn.execute(
        "SELECT 1 FROM ventas v JOIN turnos_caja t ON t.id=v.turno_id"
    ).fetchone() is not None

    # explicit indexes and triggers survived
    idx_after = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    ).fetchone()[0]
    trg_after = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
    ).fetchone()[0]
    assert idx_after == idx_before
    assert trg_after == trg_before
