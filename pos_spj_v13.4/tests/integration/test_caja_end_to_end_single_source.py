"""Cadena completa de caja con el cableado real: venta → KPIs → corte Z →
auditoría + capital, cada efecto exactamente UNA vez.

Usa FinanceService, TreasuryService y `_wire_cash_events` reales sobre un
schema born-clean. Cubre los reportes de validación manual: caja no reflejaba
las ventas, el efectivo esperado era 0 y había fuentes de verdad duplicadas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from application.services.caja_application_service import CajaApplicationService
from backend.application.commands.cash_register_commands import (
    GenerateZCutCommand,
    OpenCashShiftCommand,
)
from backend.application.services.cash_register_application_service import (
    CashRegisterApplicationService,
)
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid
from core.events.event_bus import EventBus
from core.events.handlers.cash_audit_handler import CASH_AUDIT_EVENTS
from tests.integration._born_clean_db import make_db


@pytest.fixture()
def bus():
    b = EventBus()  # singleton de proceso: aislar los canales de caja
    for evento in CASH_AUDIT_EVENTS:
        b.clear_handlers(evento)
    yield b
    for evento in CASH_AUDIT_EVENTS:
        b.clear_handlers(evento)


@pytest.fixture()
def caja(bus):
    from core.events.wiring import _wire_cash_events
    from core.services.enterprise.finance_service import FinanceService
    from core.services.finance.treasury_service import TreasuryService

    conn = make_db()
    fin = FinanceService(conn)
    svc = CajaApplicationService(conn, finance_service=fin)
    fin.caja_app = svc  # misma instancia que comparte el contenedor
    treasury = TreasuryService(conn, finance_service=fin)
    _wire_cash_events(bus, SimpleNamespace(db=conn, treasury_service=treasury))
    reg = CashRegisterApplicationService(svc, publisher=bus.publish)
    return SimpleNamespace(conn=conn, svc=svc, reg=reg, fin=fin)


def _cmd(cls, branch: str, **kw):
    return cls(operation_id=str(uuid.uuid4()), branch_id=branch,
               user_name="cajera", **kw)


def _venta(conn, branch: str, total: float, forma: str) -> None:
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, total, forma_pago, estado, fecha)"
        " VALUES (?, ?, ?, ?, ?, 'completada', ?)",
        (new_uuid(), f"F-{new_uuid()[:6]}", branch, total, forma,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


def test_venta_corte_capital_y_auditoria_una_sola_vez(caja, bus):
    branch = new_uuid()
    caja.reg.open_shift(_cmd(OpenCashShiftCommand, branch, opening_amount=100.0))
    _venta(caja.conn, branch, 250.0, "Efectivo")
    _venta(caja.conn, branch, 80.0, "Tarjeta")

    # KPIs del turno reflejan lo vendido (antes: siempre 0)
    kpi = caja.svc.get_caja_kpis(branch, "cajera")
    assert kpi["total_ventas_turno"] == 330.0
    assert kpi["total_efectivo_turno"] == 250.0

    res = caja.reg.generate_z_cut(
        _cmd(GenerateZCutCommand, branch, payload={"efectivo_fisico": 350.0})
    )
    assert res.success
    # Efectivo esperado = fondo 100 + efectivo 250 (antes: siempre 0)
    assert res.data["efectivo_esperado"] == 350.0
    assert res.data["diferencia"] == 0.0

    # Capital: el efectivo del turno se consolida UNA vez y queda confirmado
    movs = caja.conn.execute(
        "SELECT amount FROM treasury_movements WHERE source_module='caja'"
    ).fetchall()
    assert [m[0] for m in movs] == [250.0]

    # Auditoría: una fila por operación (apertura + corte), sin duplicados
    acciones = sorted(
        r[0] for r in caja.conn.execute(
            "SELECT accion FROM audit_logs WHERE modulo='CAJA'"
        ).fetchall()
    )
    assert acciones == ["CORTE_Z", "TURNO_ABIERTO"]


def test_reentrega_del_evento_de_corte_no_duplica_capital(caja, bus):
    branch = new_uuid()
    caja.reg.open_shift(_cmd(OpenCashShiftCommand, branch, opening_amount=0.0))
    _venta(caja.conn, branch, 120.0, "Efectivo")
    res = caja.reg.generate_z_cut(
        _cmd(GenerateZCutCommand, branch, payload={"efectivo_fisico": 120.0})
    )
    corte = dict(res.data, cut_id=res.data["cierre_id"], branch_id=branch)
    bus.publish(EventName.CASH_Z_CUT_GENERATED.value, corte)  # re-entrega
    n = caja.conn.execute(
        "SELECT COUNT(*) FROM treasury_movements WHERE source_module='caja'"
    ).fetchone()[0]
    assert n == 1


def test_finance_service_y_caja_comparten_una_implementacion(caja):
    """El turno abierto por la ruta legacy (FinanceService) es el mismo que ve
    CajaApplicationService: no hay dos fuentes de verdad de turnos."""
    branch = new_uuid()
    turno_id = caja.fin.abrir_turno(branch, "cajera", 50.0)
    estado = caja.svc.get_estado_turno(branch, "cajera")
    assert estado and estado["id"] == turno_id
