"""WA-1 / S6 (Crítica): `wa_event_log` debe recibir el `id` (UUIDv7,
REGLA CERO) en cada INSERT.

Antes de esta corrección, `WAEventEmitter.emit()` y
`POSNotifier._insert_wa_event()` nunca proveían `id`, así que el INSERT
fallaba sistemáticamente contra el esquema real de la migración 050
(`id TEXT NOT NULL PRIMARY KEY`, sin default SQL) — silenciado por un
`except Exception: pass` desnudo (emit()) o `logger.debug` invisible
(_insert_wa_event()). El audit trail de eventos WhatsApp no se persistía en
producción sin que nada lo señalara, violando CLAUDE.md regla 12.

Este archivo usa el esquema EXACTO de
`migrations/standalone/050_wa_integration.py::run()` para `wa_event_log`
(no ejecuta migraciones completas) y verifica que ambos puntos de inserción
efectivamente escriben una fila con un id UUIDv7 válido, y que un fallo real
de inserción ahora se loguea (WARNING) en vez de silenciarse.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parents[2] / "pos_spj_v13.4"
if str(ERP_ROOT) not in sys.path:
    sys.path.insert(0, str(ERP_ROOT))
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from erp.events import WAEventEmitter
from erp.pos_notifier import POSNotifier


def _migrated_db(tmp_path, name: str = "wa_events.db") -> sqlite3.Connection:
    """`wa_event_log` con el esquema exacto de la migración 050."""
    conn = sqlite3.connect(str(tmp_path / name))
    conn.execute("""
        CREATE TABLE wa_event_log (
            id          TEXT NOT NULL    PRIMARY KEY,
            event_type  TEXT    NOT NULL,
            data_json   TEXT,
            sucursal_id TEXT,
            prioridad   INTEGER DEFAULT 5,
            timestamp   TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _assert_valid_id(row_id) -> None:
    assert isinstance(row_id, str) and row_id
    try:
        from backend.shared.ids import is_uuidv7
        assert is_uuidv7(row_id)
    except ImportError:
        import uuid
        uuid.UUID(row_id)  # al menos forma de UUID válida


def test_emit_inserts_row_with_valid_uuidv7_id(tmp_path):
    conn = _migrated_db(tmp_path)
    emitter = WAEventEmitter(db_conn=conn)

    emitter.emit("WA_TEST_EVENT", {"foo": "bar"}, sucursal_id=1, prioridad=10)

    rows = conn.execute(
        "SELECT id, event_type FROM wa_event_log WHERE event_type='WA_TEST_EVENT'"
    ).fetchall()
    assert len(rows) == 1
    row_id, event_type = rows[0]
    assert event_type == "WA_TEST_EVENT"
    _assert_valid_id(row_id)


def test_emit_logs_warning_instead_of_silently_swallowing_insert_failure(tmp_path, caplog):
    conn = _migrated_db(tmp_path)
    emitter = WAEventEmitter(db_conn=conn)
    conn.close()  # Fuerza que el INSERT falle

    with caplog.at_level("WARNING", logger="wa.events"):
        emitter.emit("WA_TEST_EVENT_FAIL", {"foo": "bar"})

    assert any("No se pudo insertar wa_event_log" in r.message for r in caplog.records)


def test_ensure_tables_schema_matches_migration_050(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "fresh.db"))
    emitter = WAEventEmitter(db_conn=conn)
    emitter.ensure_tables()

    cols = {r[1]: r for r in conn.execute("PRAGMA table_info(wa_event_log)").fetchall()}
    assert cols["id"][2].upper() == "TEXT"
    assert cols["id"][5] == 1  # pk
    assert cols["sucursal_id"][2].upper() == "TEXT"


def test_pos_notifier_insert_wa_event_includes_valid_id(tmp_path):
    conn = _migrated_db(tmp_path, "pos_notifier.db")
    notifier = POSNotifier(conn)

    notifier._insert_wa_event("TEST_EVENT", {"a": 1}, sucursal_id=1, prioridad=50)

    row = conn.execute(
        "SELECT id FROM wa_event_log WHERE event_type='TEST_EVENT'"
    ).fetchone()
    assert row is not None
    _assert_valid_id(row[0])
