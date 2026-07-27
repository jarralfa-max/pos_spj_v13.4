"""FASE 7 (merma) — WasteRepository.register_waste mints a UUIDv7 mermas id.

REGLA CERO: the mermas row identity must be a UUIDv7 (new_uuid()), not
AUTOINCREMENT. operation_id stays a distinct UUID (rule 41). Post-cut TEXT id.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.infrastructure.db.repositories.waste_repository import WasteRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE mermas (
            id TEXT PRIMARY KEY, producto_id TEXT, sucursal_id TEXT, cantidad REAL,
            unidad TEXT, motivo TEXT, costo_unitario REAL, valor_perdida REAL,
            notas TEXT, usuario TEXT, operation_id TEXT, created_at TEXT, fecha TEXT
        )
        """
    )
    c.commit()
    return c


def _entry(op_id):
    return {
        "product_id": str(uuid.uuid4()), "branch_id": str(uuid.uuid4()),
        "quantity": 2.0, "unit": "kg", "reason": "daño", "unit_cost": 10.0,
        "loss_value": 20.0, "notes": "", "user_name": "qa",
        "operation_id": op_id, "date": "2026-06-25",
    }


def test_register_waste_persists_uuid_mermas_id(conn):
    op_id = str(uuid.uuid4())
    ret = WasteRepository(conn).register_waste(_entry(op_id))
    assert ret == op_id  # contract: returns operation_id
    row = conn.execute("SELECT id, operation_id FROM mermas").fetchone()
    assert uuid.UUID(row["id"])              # row identity is a UUID, not a rowid
    assert row["id"] != row["operation_id"]  # distinct ids (rule 41)
