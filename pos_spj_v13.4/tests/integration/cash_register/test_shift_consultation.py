"""SDLC-ARQ-SHIFT-002: el gerente consulta el turno abierto por el cajero, sin
abrir otro y sin que consultar le conceda operar (§8, aceptación §15 en su
variante de una sola base; entre terminales requiere SDLC-ARQ-HYB-001)."""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions as P
from backend.application.cash_register.shift_query_service import CashShiftQueryService
from backend.application.cash_register.shift_use_cases import (
    OpenCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.domain.cash_register.exceptions import CashPermissionDeniedError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.shared.ids import new_uuid
from frontend.desktop.modules.cash_register.cash_register_presenter import CashContextError

_NOW = "2026-11-05T09:00:00+00:00"
_CAJERO = {P.ACCESS, P.VIEW_OWN_BRANCH, P.SHIFT_VIEW, P.SHIFT_OPEN, P.SHIFT_SUSPEND,
           P.MOVEMENT_VIEW}
_GERENTE = {P.ACCESS, P.VIEW_OWN_BRANCH, P.SHIFT_VIEW, P.MOVEMENT_VIEW}


class _Grants:
    def __init__(self):
        self.by_user: dict[str, set[str]] = {}

    def has_permission(self, user_id, permission_code):
        return permission_code in self.by_user.get(user_id, set())


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


class _Session:
    is_active = True

    def __init__(self, grants, *, user_id, branch_id):
        self._grants = grants
        self.user_id = user_id
        self.active_branch_id = branch_id

    def tiene_permiso(self, permission):
        return permission in self._grants.by_user.get(self.user_id, set())


class _Root:
    pass


@pytest.fixture
def cash():
    db = sqlite3.connect(":memory:")
    for name in ("176_cash_register_configuration_schema",
                 "175_cash_register_bounded_context_schema",
                 "350_replication_engine"):
        importlib.import_module(f"migrations.standalone.{name}").run(db)
    grants = _Grants()
    branch, other_branch = new_uuid(), new_uuid()
    cajero, cajero_2, gerente = new_uuid(), new_uuid(), new_uuid()
    grants.by_user = {cajero: set(_CAJERO), cajero_2: set(_CAJERO), gerente: set(_GERENTE)}
    registers = []
    for label, owner in (("Caja 1", branch), ("Caja 2", branch), ("Caja otra", other_branch)):
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                   (register, owner, label, "ACTIVE", None, _NOW, _NOW))
        db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                   (drawer, owner, register, f"Cajón {label}", "ACTIVE", _NOW, _NOW))
        db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                   (terminal, owner, register, f"POS {label}", "ACTIVE", _NOW, _NOW))
        registers.append((register, drawer, terminal))
    db.commit()
    auth = CashAuthorizationPolicy(grants, _Scopes())
    limit = CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"),
                                    hard_cap=Decimal("5000"))

    def open_shift(cashier, *, index=0, in_branch=None):
        register, drawer, terminal = registers[index]
        return OpenCashShiftUseCase(auth, limit).execute(
            db, branch_id=in_branch or branch, register_id=register, drawer_id=drawer,
            terminal_id=terminal, cashier_user_id=cashier, opening_amount=Decimal("100"),
            actor_user_id=cashier, operation_id=new_uuid()).entity_id

    def presenter(user_id, *, in_branch=None):
        root = _Root()
        root.db = db
        root.session = _Session(grants, user_id=user_id, branch_id=in_branch or branch)
        return build_cash_register_presenter(root)

    yield SimpleNamespace(db=db, grants=grants, auth=auth, branch=branch,
                          other_branch=other_branch, cajero=cajero, cajero_2=cajero_2,
                          gerente=gerente, open=open_shift, presenter=presenter)
    db.close()


def test_el_gerente_consulta_el_mismo_turno_del_cajero_sin_crear_otro(cash):
    shift_id = cash.open(cash.cajero)
    presenter = cash.presenter(cash.gerente)
    assert [row.id for row in presenter.consultable_shifts()] == [shift_id]
    assert presenter.status_cards()["shift"].startswith("Consulta")
    assert cash.db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0] == 1


def test_ve_el_turno_de_cualquier_caja_de_su_sucursal_y_de_ninguna_otra(cash):
    first = cash.open(cash.cajero, index=0)
    second = cash.open(cash.cajero_2, index=1)
    ajeno = new_uuid()
    cash.grants.by_user[ajeno] = set(_CAJERO)
    third = cash.open(ajeno, index=2, in_branch=cash.other_branch)
    assert {row.id for row in cash.presenter(cash.gerente).consultable_shifts()} == {first, second}
    assert {row.id for row in cash.presenter(cash.gerente, in_branch=cash.other_branch)
            .consultable_shifts()} == {third}


def test_consultar_no_concede_operar(cash):
    shift_id = cash.open(cash.cajero)
    presenter = cash.presenter(cash.gerente)
    assert presenter.optional_active_shift_id() is None
    with pytest.raises(CashContextError):
        presenter.active_shift_id()
    cash.grants.by_user[cash.gerente].add(P.SHIFT_SUSPEND)
    with pytest.raises(CashPermissionDeniedError):
        SuspendCashShiftUseCase(cash.auth).execute(
            cash.db, shift_id=shift_id, branch_id=cash.branch, actor_user_id=cash.gerente,
            operation_id=new_uuid(), reason="Sólo consultaba")
    assert cash.db.execute("SELECT status FROM cash_shifts WHERE id=?",
                           (shift_id,)).fetchone()[0] == "OPEN"


def test_sin_el_permiso_de_ver_turnos_no_hay_consulta(cash):
    cash.open(cash.cajero)
    cash.grants.by_user[cash.gerente].discard(P.SHIFT_VIEW)
    assert cash.presenter(cash.gerente).consultable_shifts() == ()
    with pytest.raises(CashPermissionDeniedError):
        CashShiftQueryService(cash.db, cash.auth).list_active(
            branch_id=cash.branch, requester_user_id=cash.gerente)


def test_el_turno_propio_no_se_consulta_sino_se_opera(cash):
    shift_id = cash.open(cash.cajero)
    presenter = cash.presenter(cash.cajero)
    assert presenter.optional_active_shift_id() == shift_id
    assert presenter.consultable_shifts() == ()
    assert not presenter.status_cards()["shift"].startswith("Consulta")


def test_un_turno_ya_cerrado_no_se_consulta_como_activo(cash):
    shift_id = cash.open(cash.cajero)
    cash.db.execute("UPDATE cash_shifts SET status='CANCELLED' WHERE id=?", (shift_id,))
    assert cash.presenter(cash.gerente).consultable_shifts() == ()


def test_la_consulta_respeta_la_regla_de_importes_de_un_turno_ajeno(cash):
    cash.open(cash.cajero)
    row = cash.presenter(cash.gerente).consultable_shifts()[0]
    assert row.expected_cash is None and row.opening_amount is None
    cash.grants.by_user[cash.gerente].add(P.VIEW_SENSITIVE_AMOUNTS)
    row = cash.presenter(cash.gerente).consultable_shifts()[0]
    assert row.expected_cash == Decimal("100")


# ── pantalla ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test"])


def _ledger_page(presenter, shift_id):
    from frontend.desktop.modules.cash_register.cash_ledger_page import CashLedgerPage
    return CashLedgerPage(presenter.query_service("ledger"), shift_id=shift_id,
                          presenter=presenter)


def test_movimientos_en_consulta_muestran_el_turno_y_no_dejan_operar(cash, qapp):
    shift_id = cash.open(cash.cajero)
    cash.grants.by_user[cash.gerente] |= {P.MOVEMENT_INCOME, P.MOVEMENT_WITHDRAWAL,
                                          P.MOVEMENT_REVERSE, P.SAFE_DROP_CREATE}
    page = _ledger_page(cash.presenter(cash.gerente), None)
    assert page.shown_shift_id() == shift_id
    assert page.is_consultation()
    assert page.write_actions_enabled() is False
    assert page.read_actions_enabled() is True


def test_movimientos_del_turno_propio_siguen_operando(cash, qapp):
    shift_id = cash.open(cash.cajero)
    cash.grants.by_user[cash.cajero].add(P.MOVEMENT_INCOME)
    page = _ledger_page(cash.presenter(cash.cajero), shift_id)
    assert page.shown_shift_id() == shift_id
    assert not page.is_consultation()
    assert page.write_actions_enabled() is True


def test_elegir_otro_turno_en_movimientos_cambia_a_consulta(cash, qapp):
    own = cash.open(cash.cajero, index=0)
    other = cash.open(cash.cajero_2, index=1)
    cash.grants.by_user[cash.cajero].add(P.MOVEMENT_INCOME)
    page = _ledger_page(cash.presenter(cash.cajero), own)
    page.select_shift(other)
    assert page.shown_shift_id() == other and page.is_consultation()
    assert page.write_actions_enabled() is False
    page.select_shift(own)
    assert not page.is_consultation() and page.write_actions_enabled() is True
