"""SDLC-CASH-001: la salida de efectivo de una reversa queda en el turno abierto
de quien reversa, nunca en el turno original ya cerrado.

Venta en el turno A, Corte Z de A, reversa en el turno B: B refleja la salida, A
no cambia y el efectivo de ventas de los dos cortes suma lo que quedó vendido
(lo que el Corte Z asienta contra la caja registradora,
`cash_shift_closed_handler.py`: si B no lo reconoce, la 1102 queda con residuo).
"""
from __future__ import annotations

import importlib
import json
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_use_cases import (
    CaptureBlindCountDenominationUseCase,
    ConfirmBlindCountUseCase,
    StartBlindCountUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase,
    OpenCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.application.cash_register.z_cut_use_cases import GenerateZCutUseCase
from backend.domain.cash_register.entities import CashLedgerEntry
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError,
    CashShiftNotOpenError,
    CashShiftSuspendedError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
    CashRegisterUnitOfWork,
)
from backend.shared.ids import new_uuid

_NOW = "2026-11-05T09:00:00+00:00"


class _Permissions:
    def has_permission(self, user_id, permission_code):
        return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


@pytest.fixture
def cash():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    for name in ("175_cash_register_bounded_context_schema",
                 "176_cash_register_configuration_schema",
                 "350_replication_engine"):
        importlib.import_module(f"migrations.standalone.{name}").run(db)
    branch, a, b = new_uuid(), new_uuid(), new_uuid()
    registers, denomination = [], new_uuid()
    for label in ("Caja 1", "Caja 2"):
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                   (register, branch, label, "ACTIVE", None, _NOW, _NOW))
        db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                   (drawer, branch, register, f"Cajón {label}", "ACTIVE", _NOW, _NOW))
        db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                   (terminal, branch, register, f"POS {label}", "ACTIVE", _NOW, _NOW))
        registers.append((register, drawer, terminal))
    db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
               (denomination, "MXN", "100", "$100", 1, 1, _NOW, None))
    db.execute(
        """INSERT INTO cash_difference_policies
        (id,tolerance_amount,critical_threshold,recurrence_window_days,
         recurrence_threshold,channels_json,scope_type,scope_id,active,effective_from,effective_to)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (new_uuid(), "10", "100", 30, 3, '["IN_APP"]', "BRANCH", branch, 1, _NOW, None))
    db.commit()
    auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
    limit = CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"),
                                    hard_cap=Decimal("5000"))
    service = CashSalesIntegrationService()

    def open_shift(cashier, *, index, amount="100"):
        register, drawer, terminal = registers[index]
        return OpenCashShiftUseCase(auth, limit).execute(
            db, branch_id=branch, register_id=register, drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=cashier, opening_amount=Decimal(amount), actor_user_id=cashier,
            operation_id=new_uuid()).entity_id

    def sell(cashier, amount="300"):
        sale_id = new_uuid()
        service.record_completed_sale(
            db, sale_id=sale_id, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), payment_lines={"CASH": amount}, amount_to_settle=amount)
        return sale_id

    def reverse(sale_id, actor, operation_id=None):
        return service.reverse_sale_cash(
            db, sale_id=sale_id, branch_id=branch, actor_user_id=actor,
            operation_id=operation_id or new_uuid(), reason="Devolución total")

    def close(shift_id, cashier, *, notes):
        count = StartBlindCountUseCase(auth).execute(
            db, shift_id=shift_id, branch_id=branch, counter_user_id=cashier,
            operation_id=new_uuid())
        CaptureBlindCountDenominationUseCase(auth).execute(
            db, count_id=count.entity_id, branch_id=branch, denomination_id=denomination,
            quantity=notes, actor_user_id=cashier, operation_id=new_uuid())
        ConfirmBlindCountUseCase(auth).execute(
            db, count_id=count.entity_id, branch_id=branch, actor_user_id=cashier,
            operation_id=new_uuid())
        BeginCashShiftClosingUseCase(auth).execute(
            db, shift_id=shift_id, branch_id=branch, actor_user_id=cashier,
            operation_id=new_uuid())
        return GenerateZCutUseCase(auth).execute(
            db, shift_id=shift_id, branch_id=branch, actor_user_id=cashier,
            operation_id=new_uuid())

    yield SimpleNamespace(db=db, auth=auth, branch=branch, a=a, b=b, open=open_shift, sell=sell,
                          reverse=reverse, close=close)
    db.close()


def _shift_rows(cash, shift_id):
    return cash.db.execute(
        "SELECT movement_type, direction, amount FROM cash_ledger_entries WHERE shift_id=?"
        " ORDER BY recorded_at, id", (shift_id,)).fetchall()


def _snapshot(cash, cut):
    return json.loads(cash.db.execute("SELECT snapshot_json FROM cash_cuts WHERE id=?",
                                      (cut.entity_id,)).fetchone()[0])


def test_venta_en_a_z_de_a_reversa_en_b(cash):
    shift_a = cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    z_a = cash.close(shift_a, cash.a, notes=4)
    before = _shift_rows(cash, shift_a)

    shift_b = cash.open(cash.b, index=1, amount="500")
    cash.reverse(sale_id, cash.b)

    assert _shift_rows(cash, shift_a) == before
    assert ("REVERSAL", "OUTFLOW", "300") in _shift_rows(cash, shift_b)
    z_b = cash.close(shift_b, cash.b, notes=2)
    assert Decimal(_snapshot(cash, z_b)["expected_cash"]) == Decimal("200")
    assert Decimal(_snapshot(cash, z_b)["difference"]) == Decimal("0")
    # Lo que cada Z asienta contra la caja registradora se compensa: sin residuo.
    assert Decimal(_snapshot(cash, z_a)["sales_cash"]) == Decimal("300")
    assert Decimal(_snapshot(cash, z_b)["sales_cash"]) == Decimal("-300")


def test_la_salida_va_al_turno_del_operador_aunque_el_original_siga_abierto(cash):
    shift_a = cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    shift_b = cash.open(cash.b, index=1, amount="500")
    cash.reverse(sale_id, cash.b)
    assert [row[0] for row in _shift_rows(cash, shift_a)] == ["OPENING_FLOAT", "CASH_SALE"]
    assert ("REVERSAL", "OUTFLOW", "300") in _shift_rows(cash, shift_b)


def test_en_el_mismo_turno_la_reversa_sigue_funcionando(cash):
    shift_a = cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    cash.reverse(sale_id, cash.a)
    assert ("REVERSAL", "OUTFLOW", "300") in _shift_rows(cash, shift_a)


def test_sin_turno_abierto_no_hay_reversa_de_efectivo(cash):
    shift_a = cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    cash.close(shift_a, cash.a, notes=4)
    with pytest.raises(CashShiftNotOpenError):
        cash.reverse(sale_id, cash.b)
    assert cash.db.execute("SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type='REVERSAL'"
                           ).fetchone()[0] == 0


def test_con_el_turno_suspendido_debe_reanudar_antes(cash):
    cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    shift_b = cash.open(cash.b, index=1, amount="500")
    SuspendCashShiftUseCase(cash.auth).execute(
        cash.db, shift_id=shift_b, branch_id=cash.branch, actor_user_id=cash.b,
        operation_id=new_uuid(), reason="Comida")
    with pytest.raises(CashShiftSuspendedError):
        cash.reverse(sale_id, cash.b)


def test_no_sale_mas_efectivo_del_que_hay_en_el_cajon_del_operador(cash):
    cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    cash.open(cash.b, index=1, amount="100")
    with pytest.raises(CashInvalidStateError, match="efectivo suficiente"):
        cash.reverse(sale_id, cash.b)


def test_una_venta_sin_efectivo_no_exige_turno(cash):
    sale_without_cash = new_uuid()
    result = cash.reverse(sale_without_cash, cash.b)
    assert result.idempotent


def test_reintentar_la_reversa_no_duplica_la_salida(cash):
    cash.open(cash.a, index=0)
    sale_id = cash.sell(cash.a)
    shift_b = cash.open(cash.b, index=1, amount="500")
    operation_id = new_uuid()
    cash.reverse(sale_id, cash.b, operation_id=operation_id)
    assert cash.reverse(sale_id, cash.b, operation_id=operation_id).idempotent
    assert cash.reverse(sale_id, cash.b).idempotent
    assert [row[0] for row in _shift_rows(cash, shift_b)].count("REVERSAL") == 1


# ── guardia: ningún movimiento en un turno cerrado ─────────────────────
def test_el_repositorio_no_escribe_movimientos_en_un_turno_cerrado(cash):
    shift_a = cash.open(cash.a, index=0)
    cash.close(shift_a, cash.a, notes=1)
    before = _shift_rows(cash, shift_a)
    entry = CashLedgerEntry.create(
        shift_id=shift_a, branch_id=cash.branch, movement_type=CashMovementType.MANUAL_INCOME,
        direction=CashMovementDirection.INFLOW, amount=Decimal("10"),
        operation_id=new_uuid(), recorded_by=cash.a, concept="Tarde")
    with pytest.raises(CashInvalidStateError, match="cerrado"):
        with CashRegisterUnitOfWork(cash.db) as uow:
            uow.ledger.add(entry)
    assert _shift_rows(cash, shift_a) == before
