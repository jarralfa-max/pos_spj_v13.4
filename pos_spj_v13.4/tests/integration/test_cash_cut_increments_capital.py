"""Bug 10: el corte Z consolida el efectivo del turno en tesorería/capital.

CASH_Z_CUT_GENERATED → CashCutCapitalHandler → TreasuryService.register_inflow
(movimiento confirmado, idempotente por corte).
"""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.events.handlers.cash_cut_capital_handler import CashCutCapitalHandler
from core.services.finance.treasury_service import TreasuryService
from tests.integration._born_clean_db import make_db


def _corte_payload(**over):
    base = {
        "cierre_id": new_uuid(),
        "turno_id": new_uuid(),
        "branch_id": new_uuid(),
        "user": "cajera",
        "fondo_inicial": 200.0,
        "ventas_efectivo": 800.0,
        "efectivo_esperado": 1000.0,
        "efectivo_contado": 1000.0,
        "diferencia": 0.0,
    }
    base.update(over)
    return base


def test_z_cut_registers_treasury_inflow_for_cash_sales():
    conn = make_db()
    ts = TreasuryService(conn)
    payload = _corte_payload()
    CashCutCapitalHandler(ts).handle(payload)

    row = conn.execute(
        "SELECT amount, direction FROM treasury_movements WHERE operation_id=?",
        (f"{payload['cierre_id']}:capital",),
    ).fetchone()
    assert row is not None
    assert row[0] == 800.0 and row[1] == "in"


def test_z_cut_consolidation_is_idempotent():
    conn = make_db()
    ts = TreasuryService(conn)
    payload = _corte_payload()
    handler = CashCutCapitalHandler(ts)
    handler.handle(payload)
    handler.handle(payload)  # reintento del evento
    n = conn.execute(
        "SELECT COUNT(*) FROM treasury_movements WHERE operation_id=?",
        (f"{payload['cierre_id']}:capital",),
    ).fetchone()[0]
    assert n == 1


def test_falls_back_to_expected_minus_fondo_when_no_cash_sales():
    conn = make_db()
    ts = TreasuryService(conn)
    payload = _corte_payload()
    payload.pop("ventas_efectivo")
    CashCutCapitalHandler(ts).handle(payload)
    row = conn.execute(
        "SELECT amount FROM treasury_movements WHERE operation_id=?",
        (f"{payload['cierre_id']}:capital",),
    ).fetchone()
    # esperado 1000 - fondo 200 = 800
    assert row is not None and row[0] == 800.0


def test_zero_cash_cut_registers_nothing():
    conn = make_db()
    ts = TreasuryService(conn)
    payload = _corte_payload(ventas_efectivo=0.0, efectivo_esperado=200.0, fondo_inicial=200.0)
    CashCutCapitalHandler(ts).handle(payload)
    n = conn.execute("SELECT COUNT(*) FROM treasury_movements").fetchone()[0]
    assert n == 0


def test_handler_wired_in_events_wiring():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "core" / "events" / "wiring.py").read_text(encoding="utf-8")
    assert "CashCutCapitalHandler" in src
    assert "CASH_Z_CUT_GENERATED" in src
