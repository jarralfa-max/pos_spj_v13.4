"""Proyecciones centrales de Caja, Finanzas, Crédito y Fidelidad (Slice 6), sin
PostgreSQL.

Finanzas y Fidelidad salen de sus casos de uso REALES y pasan por el mismo
lector de fuentes del motor; Caja y Crédito, de sus constructores de eventos
reales con los campos que hoy emiten los casos de uso. La batería contra
PostgreSQL real está en `tests/integration/central_pg/test_slice6_projection_pg.py`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.application.sync.central_projection import (
    ProjectionError,
    cash_cut_row,
    cash_movement_row,
    cash_reversal_row,
    cash_shift_row,
    credit_account_row,
    journal_rows,
    loyalty_transaction_row,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.customer_credit.events import build_event_payload as credit_event
from backend.infrastructure.sync.replication_sources import ReplicationSource
from backend.shared.ids import new_uuid

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
SUCURSAL, ESTACION = new_uuid(), new_uuid()


def _hechos(conn, tabla: str, fuente: str) -> list[dict]:
    lector = ReplicationSource(fuente, tabla, "record")
    salida = []
    for fila in conn.execute(f"SELECT * FROM {tabla} ORDER BY created_at, rowid"):
        nombres = [c[0] for c in conn.execute(f"SELECT * FROM {tabla} LIMIT 0").description]
        evento, _ = lector.normalize(dict(zip(nombres, tuple(fila))), station_branch_id=SUCURSAL)
        salida.append({"event_id": evento["event_id"], "event_type": evento["event_name"],
                       "aggregate_id": evento["entity_id"], "branch_id": evento["branch_id"],
                       "station_id": ESTACION, "occurred_at": T0,
                       "payload": json.loads(json.dumps(evento["payload"]))})
    return salida


def _hecho(evento: dict) -> dict:
    datos = evento.get("payload")
    if datos is None:   # evento plano (Crédito): lo que no es identidad del sobre
        datos = {k: v for k, v in evento.items() if k not in (
            "event_id", "event_name", "operation_id", "entity_id", "branch_id", "user_id",
            "timestamp")}
    return {"event_id": evento["event_id"], "event_type": evento["event_name"],
            "aggregate_id": evento.get("entity_id") or new_uuid(), "branch_id": SUCURSAL,
            "station_id": ESTACION, "occurred_at": T0,
            "payload": json.loads(json.dumps(datos))}


# ── Finanzas: asiento real de una venta a crédito ────────────────────────────
@pytest.fixture
def finanzas():
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema

    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(c)
    bootstrap_finance(c, today=date(2026, 7, 16))
    yield c
    c.close()


def test_a_real_credit_sale_entry_projects_balanced_with_its_receivable(finanzas):
    from backend.application.event_handlers.finance.sale_completed_handler import (
        SaleCompletedHandler,
    )

    cliente = new_uuid()
    SaleCompletedHandler(finanzas).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
        "customer_id": cliente, "occurred_at": "2026-07-16T12:00:00",
        "gross_total": "100.00", "net_total": "100.00",
        "settlements": [{"type": "ON_CREDIT", "amount": "100.00"}]})
    asientos = [h for h in _hechos(finanzas, "finance_outbox", "finance")
                if h["event_type"] == "JOURNAL_ENTRY_POSTED"]
    assert asientos, "la venta a crédito debió contabilizarse"
    filas = journal_rows(asientos[0])
    cargos = sum((l["debit"] for l in filas["lines"]), Decimal("0"))
    assert cargos == sum((l["credit"] for l in filas["lines"]), Decimal("0")) == Decimal("100.00")
    por_cobrar = [l for l in filas["lines"] if l["is_receivable"]]
    assert por_cobrar and por_cobrar[0]["customer_id"] == cliente
    assert por_cobrar[0]["account_code"] == "1130" and por_cobrar[0]["debit"] == Decimal("100.00")


def test_an_unbalanced_or_lineless_entry_is_never_projected(finanzas):
    base = {"event_id": new_uuid(), "event_type": "JOURNAL_ENTRY_POSTED",
            "aggregate_id": new_uuid(), "branch_id": SUCURSAL, "station_id": ESTACION,
            "occurred_at": T0,
            "payload": {"entry_date": "2026-07-16", "posting_date": "2026-07-16",
                        "total_debits": "100", "total_credits": "100",
                        "lines": [{"account_code": "1101", "debit": "100", "credit": "0"},
                                  {"account_code": "4101", "debit": "0", "credit": "99.99"}]}}
    with pytest.raises(ProjectionError, match="DESCUADRADO"):
        journal_rows(base)
    with pytest.raises(ProjectionError, match="sin renglones"):
        journal_rows({**base, "payload": {**base["payload"], "lines": []}})


# ── Fidelidad: libro de puntos real ──────────────────────────────────────────
@pytest.fixture
def fidelidad():
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_loyalty_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    c.commit()
    yield c
    c.close()


def test_central_points_match_the_station_balance_after_earn_reserve_and_confirm(fidelidad):
    from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
    from backend.application.loyalty.use_cases.ledger_use_cases import (
        AccrueLoyaltyPointsUseCase,
        ConfirmReservedLoyaltyPointsUseCase,
        ReserveLoyaltyPointsUseCase,
    )
    from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
    from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
    from backend.infrastructure.db.repositories.loyalty.account_repository import (
        LoyaltyAccountRepository,
    )
    from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork

    auth = LoyaltyAuthorizationPolicy.permissive_for_tests()
    cliente = new_uuid()
    cuenta = LoyaltyAccount.create(customer_id=cliente)
    LoyaltyAccountRepository(fidelidad).save(cuenta)
    fidelidad.commit()
    comun = dict(actor_user_id=new_uuid(), actor_branch_id=SUCURSAL)
    ganados = AccrueLoyaltyPointsUseCase(auth).execute(
        fidelidad, loyalty_account_id=cuenta.id, points_amount=Decimal("100"),
        operation_id=new_uuid(), source_module="sales", source_document_id=new_uuid(),
        sale_id=new_uuid(), **comun)
    assert ganados.success, ganados.message
    reserva = ReserveLoyaltyPointsUseCase(auth).execute(
        fidelidad, loyalty_account_id=cuenta.id, points_amount=Decimal("30"),
        operation_id=new_uuid(), source_module="sales", **comun)
    assert reserva.success, reserva.message
    confirmada = ConfirmReservedLoyaltyPointsUseCase(auth).execute(
        fidelidad, transaction_id=reserva.entity_id, operation_id=new_uuid(), **comun)
    assert confirmada.success, confirmada.message

    filas = {}
    for hecho in _hechos(fidelidad, "loyalty_outbox", "loyalty"):
        if hecho["event_type"].startswith("LOYALTY_POINTS"):
            fila = loyalty_transaction_row(hecho)
            filas[fila["transaction_id"]] = fila          # una fila por TRANSACCIÓN
    central = sum((f["points_amount"] for f in filas.values() if f["counts_toward_balance"]),
                  Decimal("0"))
    local = LoyaltyBalancePolicy.balance(
        LoyaltyUnitOfWork(fidelidad).transactions.list_for_account(cuenta.id))
    assert central == local == Decimal("70")
    assert {f["customer_id"] for f in filas.values()} == {cliente}


def test_a_points_event_without_ledger_data_is_not_invented():
    with pytest.raises(ProjectionError, match="libro"):
        loyalty_transaction_row({"event_id": new_uuid(), "branch_id": SUCURSAL,
                                 "occurred_at": T0, "payload": {"points_amount": "10"}})


# ── Caja ─────────────────────────────────────────────────────────────────────
def _caja(evento_tipo, **datos):
    return _hecho(cash_event_payload(evento_tipo, operation_id=new_uuid(),
                                     entity_id=new_uuid(), branch_id=SUCURSAL,
                                     user_id=new_uuid(), **datos))


def test_cash_movements_are_signed_from_the_drawer_and_reversals_invert():
    turno = new_uuid()
    apertura = cash_shift_row(_caja(CashEvents.SHIFT_OPENED, opening_amount="500.00",
                                    register_id=new_uuid(), cashier_user_id=new_uuid()))
    assert apertura["opening_amount"] == Decimal("500.00")
    venta = cash_movement_row(_caja(CashEvents.MOVEMENT_RECORDED, shift_id=turno,
                                    movement_type="CASH_SALE", direction="INFLOW",
                                    amount="150.00"))
    gasto = cash_movement_row(_caja(CashEvents.MOVEMENT_RECORDED, shift_id=turno,
                                    movement_type="EXPENSE", direction="OUTFLOW",
                                    amount="40.00"))
    retiro = cash_movement_row(_caja(CashEvents.SAFE_DROP_RECORDED, shift_id=turno,
                                     amount="100.00"))
    reversa = cash_reversal_row(_caja(CashEvents.MOVEMENT_REVERSED, shift_id=turno,
                                      reversal_of_id=venta["movement_id"], amount="150.00"),
                                venta["signed_amount"])
    assert [m["signed_amount"] for m in (venta, gasto, retiro, reversa)] == [
        Decimal("150.00"), Decimal("-40.00"), Decimal("-100.00"), Decimal("-150.00")]
    with pytest.raises(ProjectionError, match="antes que su movimiento"):
        cash_reversal_row(_caja(CashEvents.MOVEMENT_REVERSED, amount="1"), None)
    with pytest.raises(ProjectionError, match="dirección"):
        cash_movement_row(_caja(CashEvents.MOVEMENT_RECORDED, amount="1", direction=""))


def test_z_cut_keeps_expected_counted_and_difference_exactly():
    corte = cash_cut_row(_caja(CashEvents.Z_CUT_GENERATED, shift_id=new_uuid(),
                               document_number="Z-0007", expected_cash="1510.00",
                               counted_cash="1500.50", difference="-9.50",
                               business_date="2026-10-25"))
    assert (corte["expected_cash"], corte["counted_cash"], corte["difference"]) == (
        Decimal("1510.00"), Decimal("1500.50"), Decimal("-9.50"))


# ── Crédito ──────────────────────────────────────────────────────────────────
def test_credit_account_follows_approval_limit_and_block():
    cliente, perfil = new_uuid(), new_uuid()

    def evento(nombre, **datos):
        return _hecho(credit_event(nombre, operation_id=new_uuid(), customer_id=cliente,
                                   profile_id=perfil, user_id=new_uuid(), **datos))

    aprobada = credit_account_row(evento("CUSTOMER_CREDIT_APPROVED", credit_limit="5000.00"))
    assert (aprobada["status"], aprobada["credit_limit"]) == ("ACTIVE", Decimal("5000.00"))
    nuevo = credit_account_row(evento("CUSTOMER_CREDIT_LIMIT_UPDATED", new_limit="8000.00"))
    assert (nuevo["status"], nuevo["credit_limit"]) == (None, Decimal("8000.00"))
    bloqueada = credit_account_row(evento("CUSTOMER_CREDIT_BLOCKED"))
    assert (bloqueada["status"], bloqueada["credit_limit"]) == ("BLOCKED", None)
