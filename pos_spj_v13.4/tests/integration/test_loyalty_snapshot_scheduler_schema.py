"""loyalty_snapshots: el scheduler recalcula checkpoints con UUIDs TEXT.

Regresión del bug: `no such column: ls.ultimo_evento_id` y comparación de
UUID contra 0. El schema canónico nace con la forma checkpoint y el scheduler
no crea ni altera tablas.
"""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.services.scheduler_service import SchedulerService
from tests.integration._born_clean_db import make_db


def _seed(conn):
    cliente_id = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente Fiel', 1)",
        (cliente_id,),
    )
    venta_id = new_uuid()
    conn.execute(
        "INSERT INTO ventas (id, folio, cliente_id, total, estado) "
        "VALUES (?, 'F-001', ?, 250.0, 'completada')",
        (venta_id, cliente_id),
    )
    ev1, ev2 = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO historico_puntos (id, cliente_id, tipo, puntos, venta_id) "
        "VALUES (?, ?, 'venta', 25, ?)",
        (ev1, cliente_id, venta_id),
    )
    conn.execute(
        "INSERT INTO historico_puntos (id, cliente_id, tipo, puntos, venta_id) "
        "VALUES (?, ?, 'ajuste', 5, NULL)",
        (ev2, cliente_id),
    )
    return cliente_id, sorted([ev1, ev2])


def test_scheduler_builds_snapshot_with_uuid_checkpoint():
    conn = make_db()
    cliente_id, eventos = _seed(conn)

    sched = SchedulerService(lambda: conn, sucursal_id="", usuario="test")
    sched._recalcular_loyalty_snapshots(conn)

    snap = conn.execute(
        "SELECT id, puntos_actuales, visitas, importe_total, ultimo_evento_id "
        "FROM loyalty_snapshots WHERE cliente_id=?",
        (cliente_id,),
    ).fetchone()
    assert snap is not None
    assert snap[0], "loyalty_snapshots.id debe acuñarse con new_uuid()"
    assert snap[1] == 30                       # 25 + 5 puntos
    assert snap[2] == 1                        # una visita (tipo 'venta')
    assert snap[3] == 250.0                    # importe de la venta asociada
    assert snap[4] == eventos[-1]              # checkpoint = último UUID (orden lexicográfico)


def test_scheduler_is_incremental_and_idempotent():
    conn = make_db()
    cliente_id, _ = _seed(conn)
    sched = SchedulerService(lambda: conn, sucursal_id="", usuario="test")
    sched._recalcular_loyalty_snapshots(conn)
    before = dict(conn.execute(
        "SELECT puntos_actuales, ultimo_evento_id FROM loyalty_snapshots WHERE cliente_id=?",
        (cliente_id,),
    ).fetchone())

    # Segunda corrida sin eventos nuevos: no cambia nada
    sched._recalcular_loyalty_snapshots(conn)
    after = dict(conn.execute(
        "SELECT puntos_actuales, ultimo_evento_id FROM loyalty_snapshots WHERE cliente_id=?",
        (cliente_id,),
    ).fetchone())
    assert before == after

    # Evento nuevo (UUIDv7 posterior) sí se acumula
    conn.execute(
        "INSERT INTO historico_puntos (id, cliente_id, tipo, puntos) "
        "VALUES (?, ?, 'venta', 10)",
        (new_uuid(), cliente_id),
    )
    sched._recalcular_loyalty_snapshots(conn)
    row = conn.execute(
        "SELECT puntos_actuales, visitas FROM loyalty_snapshots WHERE cliente_id=?",
        (cliente_id,),
    ).fetchone()
    assert row[0] == before["puntos_actuales"] + 10


def test_scheduler_does_not_alter_schema():
    """El servicio no ejecuta DDL: schema canónico solo en migrations/."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "core" / "services" / "scheduler_service.py"
    text = src.read_text(encoding="utf-8")
    assert "CREATE TABLE" not in text
    assert "ALTER TABLE" not in text
    assert "COALESCE(ls.ultimo_evento_id, 0)" not in text
