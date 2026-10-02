"""Puntos por compra (decisiones del usuario, 2026-10-02).

* 1 punto por cada $10 del total pagado, redondeado hacia abajo; configurable.
* Si el crédito acumula y la vigencia (meses) se configuran en Fidelidad.
* La cuenta de puntos se abre con la primera venta cobrada del cliente.
* Devolver retira los puntos en proporción; nunca más de los que dio la compra.
* Caducar quita sólo lo que QUEDA de cada acumulación (FIFO).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers
from backend.application.loyalty.queries.program_settings_query import LoyaltyProgramSettingsQuery
from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.loyalty.use_cases.ledger_use_cases import (
    ExpireLoyaltyPointsUseCase,
    RedeemLoyaltyPointsUseCase,
)
from backend.application.loyalty.use_cases.program_settings_use_cases import (
    UpdateLoyaltyProgramSettingsUseCase,
)
from backend.domain.loyalty.policies.accrual_policy import AccrualSettings, LoyaltyAccrualPolicy
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_loyalty_schema(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT,"
              " tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.commit()
    yield c
    c.close()


def _completed(*, customer, total="198", payments=None, cashier=None, when=None):
    return {
        "event_id": new_uuid(), "entity_id": new_uuid(), "branch_id": new_uuid(),
        "user_id": cashier or new_uuid(),
        "timestamp": (when or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "payload": {"customer_id": customer, "total": total,
                    "payments": payments or [{"method": "CASH", "amount": total}]},
    }


def _balance(conn, customer):
    return LoyaltyRedemptionPreviewQuery(conn).balance(customer)


# ── regla pura ───────────────────────────────────────────────────────────────

def test_one_point_per_ten_pesos_rounded_down():
    assert LoyaltyAccrualPolicy.points_for(Decimal("198"), AccrualSettings()) == 19
    assert LoyaltyAccrualPolicy.points_for(Decimal("9.99"), AccrualSettings()) == 0


def test_expiry_adds_calendar_months():
    fecha = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert LoyaltyAccrualPolicy.expires_at(
        fecha, AccrualSettings(expiration_months=1)).startswith("2026-02-28")
    assert LoyaltyAccrualPolicy.expires_at(fecha, AccrualSettings(expiration_months=0)) is None


# ── acumulación por el bus de Ventas ────────────────────────────────────────

def test_the_first_charged_sale_opens_the_account_and_credits_points(conn):
    customer = new_uuid()
    SaleLoyaltyEventHandlers(conn).on_sale_completed(_completed(customer=customer))
    assert _balance(conn, customer) == 19


def test_replaying_the_event_does_not_credit_twice(conn):
    customer = new_uuid()
    evento = _completed(customer=customer)
    SaleLoyaltyEventHandlers(conn).on_sale_completed(evento)
    SaleLoyaltyEventHandlers(conn).on_sale_completed(evento)
    assert _balance(conn, customer) == 19


def test_a_walk_in_sale_earns_nothing(conn):
    SaleLoyaltyEventHandlers(conn).on_sale_completed(_completed(customer=None))
    assert conn.execute("SELECT COUNT(*) FROM loyalty_transactions").fetchone()[0] == 0


def test_credit_accrual_is_configurable(conn):
    conn.execute("INSERT INTO configuraciones (clave, valor) VALUES ('loyalty_credito_acumula','0')")
    customer = new_uuid()
    SaleLoyaltyEventHandlers(conn).on_sale_completed(_completed(
        customer=customer, total="300",
        payments=[{"method": "CASH", "amount": "100"}, {"method": "CREDIT", "amount": "200"}]))
    assert _balance(conn, customer) == 10


# ── devolución ───────────────────────────────────────────────────────────────

def test_returning_half_removes_half_of_the_points(conn):
    customer = new_uuid()
    evento = _completed(customer=customer, total="200")
    handlers = SaleLoyaltyEventHandlers(conn)
    handlers.on_sale_completed(evento)

    handlers.on_sale_returned({
        "event_id": new_uuid(), "entity_id": evento["entity_id"], "branch_id": new_uuid(),
        "user_id": new_uuid(),
        "payload": {"customer_id": customer, "return_id": new_uuid(), "amount": "100",
                    "sale_total": "200", "refunded_total": "100"}})

    assert _balance(conn, customer) == 10


def test_a_reversal_removes_everything_the_sale_gave(conn):
    customer = new_uuid()
    evento = _completed(customer=customer, total="200")
    handlers = SaleLoyaltyEventHandlers(conn)
    handlers.on_sale_completed(evento)
    handlers.on_sale_reversed({
        "event_id": new_uuid(), "entity_id": evento["entity_id"], "branch_id": new_uuid(),
        "user_id": new_uuid(), "payload": {"customer_id": customer, "sale_total": "200"}})
    assert _balance(conn, customer) == 0


# ── caducidad FIFO ───────────────────────────────────────────────────────────

def test_expiry_takes_only_what_is_left_of_the_old_points(conn):
    """100 en enero, canjea 80, 50 en junio: al vencer enero caducan 20, no 100."""
    customer = new_uuid()
    handlers = SaleLoyaltyEventHandlers(conn)
    hace_13_meses = datetime.now(timezone.utc) - timedelta(days=400)
    handlers.on_sale_completed(_completed(customer=customer, total="1000", when=hace_13_meses))
    account_id = conn.execute(
        "SELECT id FROM loyalty_accounts WHERE customer_id=?", (customer,)).fetchone()[0]
    RedeemLoyaltyPointsUseCase(LoyaltyAuthorizationPolicy.permissive_for_tests()).execute(
        conn, loyalty_account_id=account_id, points_amount=Decimal("80"),
        operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        source_module="sales", sale_id=new_uuid())
    assert _balance(conn, customer) == 20

    # Cobrar corre el barrido ANTES de acreditar (no hay planificador): la
    # acumulación vencida pierde sólo sus 20 restantes, no los 100 originales.
    handlers.on_sale_completed(_completed(customer=customer, total="500"))
    assert _balance(conn, customer) == 50
    caducados = conn.execute(
        "SELECT points_amount FROM loyalty_transactions WHERE transaction_type='EXPIRE'"
    ).fetchall()
    assert [Decimal(str(r[0])) for r in caducados] == [Decimal("-20")]

    ExpireLoyaltyPointsUseCase().execute(
        conn, before_iso=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        operation_id_prefix=new_uuid())
    assert _balance(conn, customer) == 50


# ── ajustes desde Fidelidad ──────────────────────────────────────────────────

def test_settings_are_edited_from_loyalty_and_apply_to_the_next_sale(conn):
    result = UpdateLoyaltyProgramSettingsUseCase(
        LoyaltyAuthorizationPolicy.permissive_for_tests()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(), pesos_per_point=Decimal("5"),
        credit_earns=False, expiration_months=6, point_value=Decimal("0.20"), min_points=50,
        max_percent=Decimal("0.3"))
    assert result.success, result.message
    settings = LoyaltyProgramSettingsQuery(conn).current()
    assert settings.accrual == AccrualSettings(Decimal("5"), False, 6)
    assert settings.redemption.min_points == 50

    customer = new_uuid()
    SaleLoyaltyEventHandlers(conn).on_sale_completed(_completed(customer=customer, total="100"))
    assert _balance(conn, customer) == 20


def test_invalid_settings_are_rejected_and_nothing_changes(conn):
    result = UpdateLoyaltyProgramSettingsUseCase(
        LoyaltyAuthorizationPolicy.permissive_for_tests()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(), pesos_per_point=Decimal("0"),
        credit_earns=True, expiration_months=12, point_value=Decimal("0.10"), min_points=0,
        max_percent=Decimal("0.5"))
    assert result.success is False
    assert conn.execute("SELECT COUNT(*) FROM configuraciones").fetchone()[0] == 0


def test_editing_settings_requires_the_program_permission(conn):
    from backend.application.loyalty.authorization import DenyAllLoyaltyPermissionCheckerForTests

    result = UpdateLoyaltyProgramSettingsUseCase(
        LoyaltyAuthorizationPolicy(DenyAllLoyaltyPermissionCheckerForTests())).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(), pesos_per_point=Decimal("5"),
        credit_earns=True, expiration_months=12, point_value=Decimal("0.10"), min_points=0,
        max_percent=Decimal("0.5"))
    assert result.success is False


# ── canje devuelto ───────────────────────────────────────────────────────────

def test_a_reversal_gives_back_the_points_redeemed_in_that_sale(conn):
    """Compra previa de $1000 (100 pts); en una venta nueva canjea 40 y gana 20
    al cobrar $200. Reversarla quita esos 20 y devuelve los 40."""
    customer = new_uuid()
    handlers = SaleLoyaltyEventHandlers(conn)
    handlers.on_sale_completed(_completed(customer=customer, total="1000"))
    account_id = conn.execute(
        "SELECT id FROM loyalty_accounts WHERE customer_id=?", (customer,)).fetchone()[0]
    venta = _completed(customer=customer, total="200")
    RedeemLoyaltyPointsUseCase(LoyaltyAuthorizationPolicy.permissive_for_tests()).execute(
        conn, loyalty_account_id=account_id, points_amount=Decimal("40"),
        operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        source_module="sales", sale_id=venta["entity_id"])
    handlers.on_sale_completed(venta)
    assert _balance(conn, customer) == 80

    reverso = {"event_id": new_uuid(), "entity_id": venta["entity_id"], "branch_id": new_uuid(),
               "user_id": new_uuid(), "payload": {"customer_id": customer, "sale_total": "200"}}
    handlers.on_sale_reversed(reverso)
    handlers.on_sale_reversed(reverso)  # reintento del despacho: no devuelve dos veces

    assert _balance(conn, customer) == 100
