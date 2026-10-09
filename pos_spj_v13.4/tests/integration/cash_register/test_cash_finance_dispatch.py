"""CASH-26 bloque 2 — el Corte Z llega a contabilidad.

Medido 2026-10-07: `cash_outbox` no tenía despachador y `CashFinanceEventRouter`
no tenía suscriptor; además el asiento del corte acreditaba la caja
registradora por TODO el esperado (fondo y custodia incluidos), cuando esa
cuenta sólo recibe lo que Ventas asienta. Aquí se recorre un turno por la
composición real de la pantalla con el bus cableado como en el arranque.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.application.cash_register.finance_wiring import (
    dispatch_cash_outbox,
    wire_cash_register,
)
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.application.cash_register.x_cut_use_cases import _sales_cash
from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
from backend.domain.finance.enums import PostingPurpose
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.shared.business_dates import local_business_date
from backend.shared.events.application_bus import get_bus, reset_bus
from backend.shared.ids import new_uuid
from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Root:
    def __init__(self, conn, session):
        self.db, self.session = conn, session


@pytest.fixture
def conn():
    reset_bus()
    c = make_db()
    # m000 aún crea las tablas previas a Finanzas canónica; la base real ya
    # las reemplazó.
    for legacy in ("journal_entries", "financial_documents", "fixed_assets"):
        c.execute(f"DROP TABLE {legacy}")
    create_finance_schema(c)
    bootstrap_finance(c, today=date.today())
    ProvisionInstallationUseCase(
        c, installation_repository=SqliteInstallationRepository(c),
        recovery_code_repository=SqliteRecoveryCodeRepository(c),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", branch_name="Centro", owner_username="duena",
              workstation_name="Caja 1", owner_password="Correct-Horse-9!",
              owner_full_name="Duena", now=T0)
    for name in ("175_cash_register_bounded_context_schema",
                 "176_cash_register_configuration_schema",
                 "306_seed_cash_register_role_permissions",
                 "307_seed_cash_register_catalogs",
                 "308_cash_difference_two_person_rule"):
        importlib.import_module(f"migrations.standalone.{name}").run(c)
    now = "2026-08-03T00:00:00+00:00"
    branch_id = c.execute("SELECT sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()[0]
    register = new_uuid()
    c.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
              (register, branch_id, "CAJA-01", "ACTIVE", None, now, now))
    c.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
              (new_uuid(), branch_id, register, "CAJON-01", "ACTIVE", now, now))
    c.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
              (new_uuid(), branch_id, register, "TER-01", "ACTIVE", now, now))
    c.commit()
    yield c
    c.close()
    reset_bus()


def _presenter(conn):
    user_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    perms = PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(
        user_id, branch_id)
    ctx = ApplicationContext(
        installation_id="", company_id="", branch_id=branch_id, branch_name="Centro",
        assigned_branch_ids=frozenset({branch_id}), workstation_id="ws", workstation_type="",
        user_id=user_id, user_name="duena", roles=("system_owner",), permissions=frozenset(perms),
        feature_context=FeatureContext.from_flags_dict({}), session_id=new_uuid())
    return build_cash_register_presenter(_Root(conn, LegacySessionAdapter(ctx))), user_id, branch_id


def _shift_with_shortage(conn):
    """Fondo 1000 + venta 600 + dotación de cambio 300 = 1900; se cuentan 1850."""
    caja, user_id, branch_id = _presenter(conn)
    caja.open_cash_shift(opening_amount=Decimal("1000.00"))
    CashSalesIntegrationService().record_completed_sale(
        conn, sale_id=new_uuid(), branch_id=branch_id, cashier_user_id=user_id,
        operation_id=new_uuid(), payment_lines=[{"type": "CASH", "amount": "600.00"}])
    conn.commit()
    caja.register_cash_movement(movement_type="MANUAL_INCOME", amount=Decimal("300.00"),
                                concept="Cambio", reason_code="CHANGE_ADDITION")
    caja.begin_cash_shift_closing()
    count = caja.start_blind_count()
    ids = {d.value: d.id for d in caja.denomination_options()}
    for value in ("1000", "500", "200", "100", "50"):
        caja.capture_blind_count_denomination(count_id=count.entity_id,
                                              denomination_id=ids[Decimal(value)], quantity=1)
    caja.confirm_blind_count(count_id=count.entity_id)
    shift_id = caja.active_shift_id()
    caja.generate_z_cut()
    return shift_id


def _closing_entry(conn, shift_id):
    with FinanceUnitOfWork(conn) as uow:
        return uow.journal_entries.find_by_posting_reference(
            "cash", shift_id, PostingPurpose.CASH_SHIFT_CLOSE)


def test_z_cut_reaches_finance_with_only_the_sales_cash(conn):
    wire_cash_register(get_bus(), conn)
    shift_id = _shift_with_shortage(conn)

    status = conn.execute(
        "SELECT status FROM cash_outbox WHERE event_name='CASH_Z_CUT_GENERATED'").fetchone()[0]
    assert status == "DISPATCHED"
    entry = _closing_entry(conn, shift_id)
    assert entry is not None and entry.is_balanced()
    # Ventas 600 salen de la caja; el faltante de 50 es gasto; 550 llegan al
    # efectivo general. Fondo (1000) y dotación (300) son custodia: no tocan la caja.
    assert entry.total_debits().to_string() == "600.00"
    amounts = sorted((line.debit.to_string(), line.credit.to_string()) for line in entry.lines)
    assert amounts == [("0.00", "600.00"), ("50.00", "0.00"), ("550.00", "0.00")]


def test_without_finance_subscriber_the_z_cut_stays_pending(conn):
    shift_id = _shift_with_shortage(conn)
    row = conn.execute(
        "SELECT status FROM cash_outbox WHERE event_name='CASH_Z_CUT_GENERATED'").fetchone()
    assert row[0] == "PENDING"
    # Eventos sin efecto contable sí salen aunque nadie escuche.
    assert conn.execute("SELECT COUNT(*) FROM cash_outbox WHERE event_name='CASH_SHIFT_OPENED'"
                        " AND status='DISPATCHED'").fetchone()[0] == 1
    # En cuanto Finanzas se suscribe, el siguiente despacho lo entrega.
    wire_cash_register(get_bus(), conn)
    result = dispatch_cash_outbox(conn, get_bus())
    assert result["failed"] == 0
    entry = _closing_entry(conn, shift_id)
    assert entry is not None and entry.is_balanced()


def test_finance_failure_keeps_the_event_with_its_error(conn):
    def falla(_event):
        raise RuntimeError("sin perfil contable")
    get_bus().subscribe("CASH_Z_CUT_GENERATED", falla)
    _shift_with_shortage(conn)
    row = conn.execute("SELECT status, attempt_count, last_error FROM cash_outbox"
                       " WHERE event_name='CASH_Z_CUT_GENERATED'").fetchone()
    assert row[0] == "PENDING" and row[1] == 1 and "sin perfil contable" in row[2]


def test_sales_cash_separates_sale_reversals_from_custody_reversals():
    rows = [
        {"id": "a", "movement_type": "OPENING_FLOAT", "direction": "INFLOW", "amount": "1000"},
        {"id": "b", "movement_type": "CASH_SALE", "direction": "INFLOW", "amount": "600"},
        {"id": "c", "movement_type": "CASH_SALE", "direction": "INFLOW", "amount": "80"},
        {"id": "d", "movement_type": "REVERSAL", "direction": "OUTFLOW", "amount": "80",
         "reversal_of_id": "c"},
        {"id": "e", "movement_type": "MANUAL_INCOME", "direction": "INFLOW", "amount": "300"},
        {"id": "f", "movement_type": "REVERSAL", "direction": "OUTFLOW", "amount": "300",
         "reversal_of_id": "e"},
        {"id": "g", "movement_type": "CASH_REFUND", "direction": "OUTFLOW", "amount": "20"},
        {"id": "h", "movement_type": "SAFE_DROP", "direction": "OUTFLOW", "amount": "100"},
    ]
    assert _sales_cash(rows) == Decimal("580")


def test_shift_business_date_dates_the_closing_entry(conn):
    """§33: el turno guarda su día local de apertura y el asiento del Z lo usa."""
    wire_cash_register(get_bus(), conn)
    shift_id = _shift_with_shortage(conn)
    business_date, opened_at = conn.execute(
        "SELECT business_date, opened_at FROM cash_shifts WHERE id=?", (shift_id,)).fetchone()
    assert business_date == local_business_date(opened_at).isoformat()
    assert _closing_entry(conn, shift_id).entry_date.isoformat() == business_date


def test_a_z_cut_after_six_pm_posts_on_the_shift_day_not_the_utc_day(conn):
    from backend.application.event_handlers.finance.cash_finance_router import (
        CashFinanceEventRouter,
    )

    shift_id = new_uuid()
    CashFinanceEventRouter(conn).handle({
        "event_id": new_uuid(), "event_name": "CASH_Z_CUT_GENERATED",
        "operation_id": new_uuid(), "entity_id": new_uuid(), "branch_id": new_uuid(),
        # 20:30 del 30 de septiembre en México = 02:30 UTC del 1 de octubre.
        "timestamp": "2026-10-01T02:30:00+00:00",
        "payload": {"shift_id": shift_id, "expected_cash": "100.00",
                    "counted_cash": "100.00", "sales_cash": "100.00",
                    "business_date": "2026-09-30"}})
    assert _closing_entry(conn, shift_id).entry_date == date(2026, 9, 30)
