"""SDLC-CASH-002: Tesorería confirma el depósito con su ticket y el banco se
asienta una sola vez, ligado al `deposit_id`.

Respuesta del responsable (intent): confirma tesorería, con ticket. Se recorre
la cadena real: safe drop → entrega recibida → depósito preparado por Caja →
confirmado por Tesorería → `dispatch_finance_outbox` con Finanzas suscrita como
en el arranque. Caja nunca confirma: su catálogo prohíbe `CASH_DEPOSIT_CONFIRMED`
(`test_cash_register_domain_contract.py`).
"""
from __future__ import annotations

import importlib
import sqlite3
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.finance_wiring import (
    FINANCE_EVENTS,
    dispatch_cash_outbox,
    wire_cash_register,
)
from backend.application.cash_register.movement_use_cases import (
    DeliverTreasuryHandoverUseCase,
    PrepareCashDepositUseCase,
    PrepareTreasuryHandoverUseCase,
    ReceiveTreasuryHandoverUseCase,
    RegisterSafeDropUseCase,
)
from backend.application.cash_register.operational_read_query_service import (
    CashOperationalReadQueryService,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions as P
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.finance.authorization import FinanceAuthorizationPolicy
from backend.application.finance.finance_commands import FinanceCommandService
from backend.application.finance.permissions import FinancePermissions
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.application.services.finance.outbox_dispatcher import (
    REQUIRES_CONSUMER,
    dispatch_finance_outbox,
)
from backend.application.use_cases.finance.confirm_cash_deposit_use_case import (
    ConfirmCashDepositUseCase,
)
from backend.domain.cash_register.events import ALL_CASH_EVENTS
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError,
    CashPermissionDeniedError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.domain.finance.enums import PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError, PermissionDeniedError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.shared.events.application_bus import get_bus, reset_bus
from backend.shared.ids import new_uuid

_NOW = "2026-01-01T09:00:00+00:00"


class _Grants:
    def __init__(self):
        self.denied: dict[str, set[str]] = {}

    def has_permission(self, user_id, permission_code):
        return (permission_code in ALL_CASH_PERMISSIONS
                and permission_code not in self.denied.get(user_id, set()))


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


@pytest.fixture
def cash():
    reset_bus()
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    create_finance_schema(db)
    bootstrap_finance(db, today=date.today())
    for name in ("175_cash_register_bounded_context_schema",
                 "176_cash_register_configuration_schema",
                 "307_seed_cash_register_catalogs",
                 "350_replication_engine",
                 "360_cash_deposit_confirmations"):
        importlib.import_module(f"migrations.standalone.{name}").run(db)
    grants = _Grants()
    auth = CashAuthorizationPolicy(grants, _Scopes())
    limit = CashMonetaryLimitPolicy(approval_threshold=Decimal("100000"),
                                    hard_cap=Decimal("500000"))
    branch, cashier, treasurer = new_uuid(), new_uuid(), new_uuid()
    register, drawer, terminal, denomination = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
               (register, branch, "Caja", "ACTIVE", None, _NOW, _NOW))
    db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
               (drawer, branch, register, "Cajón", "ACTIVE", _NOW, _NOW))
    db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
               (terminal, branch, register, "POS", "ACTIVE", _NOW, _NOW))
    db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
               (denomination, "MXN", "100", "$100", 1, 1, _NOW, None))
    reason = db.execute(
        "SELECT code FROM cash_movement_reasons WHERE movement_type='SAFE_DROP'"
        " AND requires_authorization=0 AND active=1").fetchone()[0]
    db.commit()
    wire_cash_register(get_bus(), db)
    shift_id = OpenCashShiftUseCase(auth, limit).execute(
        db, branch_id=branch, register_id=register, drawer_id=drawer, terminal_id=terminal,
        cashier_user_id=cashier, opening_amount=Decimal("500"), actor_user_id=cashier,
        operation_id=new_uuid()).entity_id

    def received_handover(notes=3):
        lines = {denomination: notes}
        drop = RegisterSafeDropUseCase(auth, limit).execute(
            db, shift_id=shift_id, branch_id=branch, amount=Decimal(100 * notes),
            reason_code=reason, actor_user_id=cashier, operation_id=new_uuid())
        handover = PrepareTreasuryHandoverUseCase(auth).execute(
            db, safe_drop_entry_id=drop.entity_id, branch_id=branch, actor_user_id=cashier,
            operation_id=new_uuid(), denominations=lines).entity_id
        DeliverTreasuryHandoverUseCase(auth).execute(
            db, handover_id=handover, branch_id=branch, actor_user_id=cashier,
            operation_id=new_uuid(), denominations=lines)
        ReceiveTreasuryHandoverUseCase(auth).execute(
            db, handover_id=handover, branch_id=branch, actor_user_id=treasurer,
            operation_id=new_uuid(), denominations=lines)
        return handover

    def prepare(handover_id, *, actor=None, operation_id=None):
        return PrepareCashDepositUseCase(auth).execute(
            db, handover_id=handover_id, branch_id=branch, actor_user_id=actor or cashier,
            operation_id=operation_id or new_uuid())

    def confirm(deposit_id, *, actor=None, ticket="TICKET-8841", operation_id=None):
        return ConfirmCashDepositUseCase().execute(
            db, deposit_id=deposit_id, ticket_reference=ticket,
            confirmed_by=actor or treasurer, operation_id=operation_id or new_uuid())

    yield SimpleNamespace(db=db, auth=auth, grants=grants, branch=branch, cashier=cashier,
                          treasurer=treasurer, received_handover=received_handover,
                          prepare=prepare, confirm=confirm)
    db.close()
    reset_bus()


def _deposit_entries(cash, deposit_id):
    with FinanceUnitOfWork(cash.db) as uow:
        return uow.journal_entries.find_by_posting_reference(
            "treasury", deposit_id, PostingPurpose.CASH_DEPOSIT)


def _deposit_count(cash):
    return cash.db.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='CASH_DEPOSIT'").fetchone()[0]


def test_la_confirmacion_es_de_tesoreria_y_finanzas_la_atiende():
    assert "TREASURY_CASH_DEPOSIT_CONFIRMED" in FINANCE_EVENTS
    assert "TREASURY_CASH_DEPOSIT_CONFIRMED" in REQUIRES_CONSUMER
    assert "CASH_DEPOSIT_CONFIRMED" not in ALL_CASH_EVENTS


def test_confirmar_el_deposito_asienta_al_banco_una_vez(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    cash.confirm(deposit_id)
    result = dispatch_finance_outbox(cash.db, get_bus())
    assert result["failed"] == 0
    entry = _deposit_entries(cash, deposit_id)
    assert entry is not None and entry.is_balanced()
    assert _deposit_count(cash) == 1
    dispatch_finance_outbox(cash.db, get_bus())
    assert _deposit_count(cash) == 1


def test_preparar_no_asienta_nada(cash):
    cash.prepare(cash.received_handover())
    dispatch_cash_outbox(cash.db, get_bus())
    dispatch_finance_outbox(cash.db, get_bus())
    assert _deposit_count(cash) == 0


def test_el_importe_es_el_del_deposito(cash):
    deposit_id = cash.prepare(cash.received_handover(notes=4)).entity_id
    cash.confirm(deposit_id)
    assert cash.db.execute("SELECT amount FROM cash_deposit_confirmations WHERE deposit_id=?",
                           (deposit_id,)).fetchone()[0] == "400"


def test_reintentar_o_confirmar_dos_veces_es_una_sola_operacion(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    operation_id = new_uuid()
    first = cash.confirm(deposit_id, operation_id=operation_id)
    assert cash.confirm(deposit_id, operation_id=operation_id) == first
    assert cash.confirm(deposit_id) == first
    dispatch_finance_outbox(cash.db, get_bus())
    assert _deposit_count(cash) == 1


def test_preparar_dos_veces_la_misma_entrega_es_el_mismo_deposito(cash):
    handover = cash.received_handover()
    first = cash.prepare(handover)
    assert cash.prepare(handover).entity_id == first.entity_id
    assert cash.prepare(handover).idempotent


def test_el_ticket_es_obligatorio(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    with pytest.raises(FinanceDomainError, match="ticket"):
        cash.confirm(deposit_id, ticket="   ")
    assert cash.db.execute("SELECT COUNT(*) FROM cash_deposit_confirmations").fetchone()[0] == 0


def test_el_ticket_queda_ligado_y_en_el_evento(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    cash.confirm(deposit_id, ticket="  TK-77 ")
    assert cash.db.execute("SELECT ticket_reference FROM cash_deposit_confirmations"
                           " WHERE deposit_id=?", (deposit_id,)).fetchone()[0] == "TK-77"
    payload = cash.db.execute(
        "SELECT payload_json FROM finance_outbox"
        " WHERE event_name='TREASURY_CASH_DEPOSIT_CONFIRMED'").fetchone()[0]
    assert "TK-77" in payload and deposit_id in payload


def test_quien_preparo_no_confirma(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    with pytest.raises(PermissionDeniedError):
        cash.confirm(deposit_id, actor=cash.cashier)


def _commands(cash, *, granted):
    class _Checker:
        def has_permission(self, user_id, permission_code):
            return permission_code in granted

    return FinanceCommandService(
        connection_provider=lambda: cash.db,
        use_cases={"confirm_cash_deposit": ConfirmCashDepositUseCase()},
        authorization=FinanceAuthorizationPolicy(_Checker()),
        actor_provider=lambda: cash.treasurer,
        after_command=lambda: dispatch_finance_outbox(cash.db, get_bus()))


def test_confirmar_exige_el_permiso_de_tesoreria(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    with pytest.raises(PermissionDeniedError):
        _commands(cash, granted=set()).confirm_cash_deposit(
            deposit_id=deposit_id, ticket_reference="TK-1")
    assert _deposit_count(cash) == 0


def test_el_comando_de_tesoreria_deja_el_asiento_hecho(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    _commands(cash, granted={FinancePermissions.TREASURY_MOVEMENT}).confirm_cash_deposit(
        deposit_id=deposit_id, ticket_reference="TK-1")
    assert _deposit_entries(cash, deposit_id) is not None


def test_preparar_exige_su_permiso(cash):
    handover = cash.received_handover()
    cash.grants.denied[cash.cashier] = {P.DEPOSIT_PREPARE}
    with pytest.raises(CashPermissionDeniedError):
        cash.prepare(handover)


def test_no_se_prepara_una_entrega_que_tesoreria_no_recibio(cash):
    with pytest.raises(CashInvalidStateError):
        cash.prepare(new_uuid())


def test_no_se_confirma_un_deposito_inexistente(cash):
    with pytest.raises(FinanceDomainError):
        cash.confirm(new_uuid())


def test_tesoreria_solo_ve_los_depositos_por_confirmar(cash):
    from backend.application.queries.finance.treasury_query_service import TreasuryQueryService

    deposit_id = cash.prepare(cash.received_handover()).entity_id
    query = TreasuryQueryService(cash.db)
    assert [row["id"] for row in query.pending_cash_deposits()] == [deposit_id]
    cash.confirm(deposit_id)
    assert query.pending_cash_deposits() == []


def test_la_pantalla_de_caja_lista_cada_deposito_con_su_estado(cash):
    deposit_id = cash.prepare(cash.received_handover()).entity_id
    query = CashOperationalReadQueryService(cash.db, cash.auth)

    def rows():
        return query.section(section_key="deposits", branch_id=cash.branch,
                             requester_user_id=cash.treasurer).rows

    assert [(row.id, row.status) for row in rows()] == [(deposit_id, "PREPARED")]
    cash.confirm(deposit_id)
    assert [(row.id, row.status) for row in rows()] == [(deposit_id, "CONFIRMED")]


def test_tesoreria_tiene_la_accion_en_su_pantalla():
    from frontend.desktop.modules.finance.pages.treasury_page import TreasuryPage

    assert ("Confirmar depósito", FinancePermissions.TREASURY_MOVEMENT, "_confirm_deposit",
            False) in TreasuryPage.header_actions
