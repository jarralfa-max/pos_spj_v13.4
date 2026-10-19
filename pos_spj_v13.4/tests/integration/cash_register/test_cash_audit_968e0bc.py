"""Auditoría de Caja 968e0bc (2026-10-16) — un caso por hallazgo, con
pruebas NEGATIVAS por usuario, turno, sucursal y arqueo abierto."""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_use_cases import StartBlindCountUseCase
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions
from backend.application.cash_register.session_authorization import (
    CashSessionBranchScopeChecker,
)
from backend.application.cash_register.shift_query_service import CashShiftQueryService
from backend.application.cash_register.shift_use_cases import (
    OpenCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.domain.cash_register.exceptions import CashPermissionDeniedError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.repositories import CashLedgerRepository
from backend.shared.ids import new_uuid

_CASHIER_ONLY = {
    CashPermissions.ACCESS, CashPermissions.VIEW_OWN_BRANCH, CashPermissions.SHIFT_VIEW,
    CashPermissions.SHIFT_OPEN, CashPermissions.SHIFT_SUSPEND, CashPermissions.SHIFT_RESUME,
    CashPermissions.SHIFT_PREPARE_CLOSE, CashPermissions.MOVEMENT_VIEW,
    CashPermissions.BLIND_COUNT_START, CashPermissions.BLIND_COUNT_VIEW,
}


class _Grants:
    """user_id → permisos (gerente: todos; cajeros: los de fábrica)."""

    def __init__(self):
        self.by_user: dict[str, set[str]] = {}

    def has_permission(self, user_id, permission_code):
        return permission_code in self.by_user.get(user_id, set())


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


@pytest.fixture
def cash():
    db = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(db)
    grants = _Grants()
    auth = CashAuthorizationPolicy(grants, _Scopes())
    branch, cajero_a, cajero_b, gerente = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    grants.by_user = {cajero_a: set(_CASHIER_ONLY), cajero_b: set(_CASHIER_ONLY),
                      gerente: set(ALL_CASH_PERMISSIONS)}
    now = "2026-10-16T09:00:00+00:00"
    registers = []
    for name in ("Caja 1", "Caja 2"):
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                   (register, branch, name, "ACTIVE", None, now, now))
        db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                   (drawer, branch, register, f"Cajón {name}", "ACTIVE", now, now))
        db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                   (terminal, branch, register, f"POS {name}", "ACTIVE", now, now))
        registers.append((register, drawer, terminal))
    db.commit()
    limit = CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))

    def open_shift(cashier, *, actor=None, index=0, amount="500"):
        register, drawer, terminal = registers[index]
        return OpenCashShiftUseCase(auth, limit).execute(
            db, branch_id=branch, register_id=register, drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=cashier, opening_amount=Decimal(amount),
            actor_user_id=actor or cashier, operation_id=new_uuid()).entity_id

    yield SimpleNamespace(db=db, auth=auth, grants=grants, branch=branch, a=cajero_a, b=cajero_b,
                          gerente=gerente, open=open_shift, registers=registers)
    db.close()


def _ledger(cash):
    return CashLedgerQueryService(CashLedgerRepository(cash.db), connection=cash.db,
                                  authorization=cash.auth)


def _start_count(cash, shift, counter):
    return StartBlindCountUseCase(cash.auth).execute(
        cash.db, shift_id=shift, branch_id=cash.branch, counter_user_id=counter,
        operation_id=new_uuid())


# ── CJA-01 ───────────────────────────────────────────────────────────────
class TestBlindCountDoesNotLeak:
    def test_the_ledger_hides_the_balance_during_the_count(self, cash):
        shift = cash.open(cash.a)
        _start_count(cash, shift, cash.a)
        own = _ledger(cash).projection(shift, requester_user_id=cash.a, branch_id=cash.branch)
        assert own.balance is None and own.inflows is None
        assert all(r.amount is None and r.balance is None for r in own.rows)
        assert "arqueo" in own.hidden_reason
        # El supervisor (ver esperado) sí lo ve; el cajero en conteo, nunca.
        sup = _ledger(cash).projection(shift, requester_user_id=cash.gerente,
                                       branch_id=cash.branch)
        assert sup.balance == Decimal("500")

    def test_the_shift_list_also_hides_it(self, cash):
        shift = cash.open(cash.a)
        _start_count(cash, shift, cash.a)
        row = CashShiftQueryService(cash.db, cash.auth).list_recent(
            branch_id=cash.branch, requester_user_id=cash.a).rows[0]
        assert row.expected_cash is None

    def test_another_cashiers_amounts_need_sensitive_permission(self, cash):
        shift = cash.open(cash.a)
        other = _ledger(cash).projection(shift, requester_user_id=cash.b, branch_id=cash.branch)
        assert other.balance is None and "otro cajero" in other.hidden_reason
        own = _ledger(cash).projection(shift, requester_user_id=cash.a, branch_id=cash.branch)
        assert own.balance == Decimal("500")

    def test_the_ledger_requires_user_permission_and_branch(self, cash):
        shift = cash.open(cash.a)
        with pytest.raises(Exception):
            _ledger(cash).projection(shift)                     # sin usuario
        with pytest.raises(Exception):
            _ledger(cash).projection(shift, requester_user_id=cash.a, branch_id=new_uuid())


# ── CJA-02 ───────────────────────────────────────────────────────────────
class TestShiftOwnership:
    def test_a_cashier_cannot_suspend_another_cashiers_shift(self, cash):
        shift = cash.open(cash.a)
        with pytest.raises(CashPermissionDeniedError, match="otro cajero"):
            SuspendCashShiftUseCase(cash.auth).execute(
                cash.db, shift_id=shift, branch_id=cash.branch, actor_user_id=cash.b,
                operation_id=new_uuid(), reason="me equivoqué")
        assert cash.db.execute("SELECT status FROM cash_shifts WHERE id=?",
                               (shift,)).fetchone()[0] == "OPEN"

    def test_a_supervisor_intervenes_with_a_reason_and_it_is_recorded(self, cash):
        shift = cash.open(cash.a)
        with pytest.raises(CashPermissionDeniedError, match="motivo"):
            SuspendCashShiftUseCase(cash.auth).execute(
                cash.db, shift_id=shift, branch_id=cash.branch, actor_user_id=cash.gerente,
                operation_id=new_uuid(), reason="")
        SuspendCashShiftUseCase(cash.auth).execute(
            cash.db, shift_id=shift, branch_id=cash.branch, actor_user_id=cash.gerente,
            operation_id=new_uuid(), reason="Cajero enfermo")
        payload = cash.db.execute(
            "SELECT payload_json FROM cash_outbox WHERE event_name='CASH_SHIFT_SUSPENDED'"
        ).fetchone()[0]
        import json
        event = json.loads(payload)
        assert (event.get("payload") or event)["intervention"] is True

    def test_nobody_opens_a_shift_for_someone_else_without_reassign(self, cash):
        with pytest.raises(CashPermissionDeniedError, match="propio turno"):
            cash.open(cash.a, actor=cash.b)
        assert cash.open(cash.a, actor=cash.gerente)           # gerente: reasignar

    def test_counting_another_cashiers_drawer_is_for_supervisors(self, cash):
        shift = cash.open(cash.a)
        with pytest.raises(CashPermissionDeniedError):
            _start_count(cash, shift, cash.b)
        assert _start_count(cash, shift, cash.gerente).entity_id   # arqueo sorpresa


# ── CJA-04 ───────────────────────────────────────────────────────────────
def test_startup_drains_the_cash_outbox(monkeypatch):
    from backend.application.cash_register import finance_wiring
    from backend.bootstrap.wiring import event_wiring
    called = []
    monkeypatch.setattr(finance_wiring, "dispatch_cash_outbox",
                        lambda connection, bus, **k: called.append(connection) or {})
    conn = sqlite3.connect(":memory:")
    try:
        event_wiring.wire_cross_context_events(conn)
    except Exception:  # noqa: BLE001 - base vacía: otros cableados pueden fallar
        pass
    assert called, "el arranque no despachó cash_outbox"


# ── CJA-05 ───────────────────────────────────────────────────────────────
def test_cut_tickets_print_real_symbols_not_uuid_text():
    from backend.application.cash_register.printing import (
        CashPrintDocument,
        CashPrintDocumentType,
    )
    from backend.infrastructure.printing.cash_register_renderers import CashDocumentEscPosRenderer

    document = CashPrintDocument(
        document_type=CashPrintDocumentType.Z_CUT, entity_id=new_uuid(), branch_id=new_uuid(),
        reference="CZ-2026-000001", title="Corte Z", fields=(("Caja", "Caja 1"),),
        barcode_value="CZ-2026-000001")
    data = CashDocumentEscPosRenderer(paper_width_mm=80).render(document).content
    assert b"\x1dv0" in data and b"BARCODE:" not in data and b"QR:" not in data
    assert b"CZ-2026-000001" in data


# ── CJA-06 ───────────────────────────────────────────────────────────────
def test_a_role_with_the_cut_permission_alone_can_print_it():
    from backend.application.cash_register.printing import (
        CashPrintDocument,
        CashPrintDocumentType,
        CashPrintFormat,
        PrintCashDocumentCommand,
        PrintCashDocumentUseCase,
    )
    from backend.infrastructure.printing.cash_register_renderers import CashDocumentEscPosRenderer

    actor, branch = new_uuid(), new_uuid()
    grants = _Grants()
    grants.by_user = {actor: {CashPermissions.X_CUT_PRINT}}       # SIN el genérico CAJA.imprimir
    queued = []

    class Store:
        def print_id_for_operation(self, op): return None
        def original_exists(self, *a): return False
        def enqueue(self, *args, **kwargs): queued.append(1)
        def record(self, *args, **kwargs): pass

    use_case = PrintCashDocumentUseCase(
        authorization=CashAuthorizationPolicy(grants, _Scopes()),
        renderers={CashPrintFormat.ESC_POS: CashDocumentEscPosRenderer()},
        queue=Store(), audit=Store())
    document = CashPrintDocument(
        document_type=CashPrintDocumentType.X_CUT, entity_id=new_uuid(), branch_id=branch,
        reference="CX-1", title="Corte X", fields=(("Caja", "Caja 1"),))
    try:
        use_case.execute(PrintCashDocumentCommand(
            operation_id=new_uuid(), actor_user_id=actor, document=document,
            printer_id="termica", output_format=CashPrintFormat.ESC_POS,
            permission_code=CashPermissions.X_CUT_PRINT))
    except CashPermissionDeniedError:
        pytest.fail("el permiso del corte debe bastar")
    except Exception:  # noqa: BLE001 - el doble de la cola es mínimo; basta pasar el permiso
        pass


# ── CJA-07 ───────────────────────────────────────────────────────────────
class TestRegisterChoice:
    def _resolver(self, cash, user):
        from backend.infrastructure.desktop.cash_operational_context import (
            DesktopCashOperationalContextResolver,
        )
        session = SimpleNamespace(user_id=user, active_branch_id=cash.branch, is_active=True)
        return DesktopCashOperationalContextResolver(cash.db, session, SimpleNamespace())

    def test_with_two_free_registers_nothing_is_guessed(self, cash):
        resolver = self._resolver(cash, cash.a)
        assert resolver.context().cash_register_id is None
        options = resolver.available_registers()
        assert [o["register_name"] for o in options] == ["Caja 1", "Caja 2"]
        resolver.choose_register(options[1]["register_id"])
        assert resolver.context().cash_register_id == options[1]["register_id"]

    def test_a_busy_register_is_not_offered_and_the_free_one_is_used(self, cash):
        cash.open(cash.b, index=0)
        resolver = self._resolver(cash, cash.a)
        options = resolver.available_registers()
        assert [o["busy"] for o in options] == [True, False]
        assert resolver.context().cash_register_id == cash.registers[1][0]


# ── CJA-08 ───────────────────────────────────────────────────────────────
def test_assigned_branches_are_honoured():
    active, assigned, other = new_uuid(), new_uuid(), new_uuid()
    user = new_uuid()
    session = SimpleNamespace(
        is_active=True, user_id=user, active_branch_id=active,
        assigned_branch_ids=frozenset({active, assigned}),
        tiene_permiso=lambda code: code == CashPermissions.VIEW_ASSIGNED_BRANCHES)
    checker = CashSessionBranchScopeChecker(session)
    assert checker.can_access_branch(user_id=user, branch_id=active)
    assert checker.can_access_branch(user_id=user, branch_id=assigned)
    assert not checker.can_access_branch(user_id=user, branch_id=other)


# ── Cierre de pendientes (2026-10-16) ─────────────────────────────────────
def test_handover_amounts_follow_who_prepared_or_receives(cash):
    from backend.application.cash_register.handover_query_service import CashHandoverQueryService
    from backend.infrastructure.db.repositories.cash_register.repositories import (
        CashHandoverRepository,
    )
    shift = cash.open(cash.a)
    source = new_uuid()
    cash.db.execute(
        "INSERT INTO cash_ledger_entries (id,shift_id,branch_id,movement_type,direction,amount,"
        "operation_id,recorded_by,concept,reference_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (source, shift, cash.branch, "SAFE_DROP", "OUTFLOW", "50.00", new_uuid(), cash.a,
         "Retiro", new_uuid(), "2026-10-16T10:00:00+00:00"))
    cash.db.execute(
        "INSERT INTO cash_handovers (id,shift_id,branch_id,amount,prepared_by,operation_id,"
        "source_entry_id,status,prepared_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (new_uuid(), shift, cash.branch, "50.00", cash.a, new_uuid(), source, "PREPARED",
         "2026-10-16T10:05:00+00:00"))
    cash.db.commit()
    for user in (cash.a, cash.b):
        cash.grants.by_user[user].add(CashPermissions.HANDOVER_VIEW)
    query = CashHandoverQueryService(CashHandoverRepository(cash.db), connection=cash.db,
                                     authorization=cash.auth)
    own = query.list_for_branch(cash.branch, requester_user_id=cash.a)[0]
    other = query.list_for_branch(cash.branch, requester_user_id=cash.b)[0]
    boss = query.list_for_branch(cash.branch, requester_user_id=cash.gerente)[0]
    assert own.amount == Decimal("50.00") and boss.amount == Decimal("50.00")
    assert other.amount is None
    with pytest.raises(Exception):
        query.list_for_branch(cash.branch)                       # sin usuario


def test_ledger_rows_carry_readable_origin(cash):
    shift = cash.open(cash.a)
    row = _ledger(cash).projection(shift, requester_user_id=cash.a, branch_id=cash.branch).rows[0]
    assert row.origin_label == "Apertura del turno"
