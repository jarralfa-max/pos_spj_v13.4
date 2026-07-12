"""Caja acepta movimientos manuales directos del módulo Caja (y solo esos)."""
from __future__ import annotations

import pytest

from application.services.caja_application_service import CajaApplicationService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _svc(conn):
    svc = CajaApplicationService.__new__(CajaApplicationService)
    svc.db = conn
    svc._publish = lambda *a, **k: None
    return svc


def test_manual_income_and_withdrawal_are_recorded():
    conn = make_db()
    svc = _svc(conn)
    turno_id, sucursal_id = new_uuid(), new_uuid()

    svc.registrar_movimiento_manual(turno_id, sucursal_id, "cajero1", "INGRESO", 200.0, "Fondo extra")
    svc.registrar_movimiento_manual(turno_id, sucursal_id, "cajero1", "RETIRO", 50.0, "Retiro parcial")

    rows = conn.execute(
        "SELECT id, tipo, monto FROM movimientos_caja WHERE turno_id=? ORDER BY tipo",
        (turno_id,),
    ).fetchall()
    assert len(rows) == 2
    assert all(r[0] for r in rows), "movimientos_caja.id debe ser UUID (new_uuid)"
    assert rows[0][1] == "INGRESO" and rows[0][2] == 200.0
    assert rows[1][1] == "RETIRO" and rows[1][2] == 50.0


def test_invalid_amount_or_type_rejected():
    conn = make_db()
    svc = _svc(conn)
    with pytest.raises(ValueError):
        svc.registrar_movimiento_manual(new_uuid(), new_uuid(), "u", "INGRESO", 0, "x")
    with pytest.raises(ValueError):
        svc.registrar_movimiento_manual(new_uuid(), new_uuid(), "u", "OTRO", 10, "x")
