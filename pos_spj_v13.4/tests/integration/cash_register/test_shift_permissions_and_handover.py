"""SDLC-ARQ-SHIFT-003: permisos de caja que de verdad se verifican y entrega de
un turno vivo entre cajeros (decisión 2026-11-02: la entrega existe; revisar el
Corte Z no es obligatorio antes de cerrar)."""
from __future__ import annotations

import importlib
import json
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_use_cases import RegisterCashMovementUseCase
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions as P
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase,
    OpenCashShiftUseCase,
    ReassignCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.application.cash_register.z_cut_use_cases import (
    GenerateZCutUseCase,
    ReviewZCutUseCase,
)
from backend.domain.cash_register.enums import CashMovementType
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError,
    CashPermissionDeniedError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.shared.ids import new_uuid

_NOW = "2026-11-05T09:00:00+00:00"
_CAJERO = {P.ACCESS, P.VIEW_OWN_BRANCH, P.SHIFT_VIEW, P.SHIFT_OPEN, P.SHIFT_SUSPEND,
           P.SHIFT_RESUME, P.SHIFT_PREPARE_CLOSE, P.MOVEMENT_INCOME, P.MOVEMENT_WITHDRAWAL}


class _Grants:
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
    for name in ("176_cash_register_configuration_schema",
                 "175_cash_register_bounded_context_schema",
                 "307_seed_cash_register_catalogs",
                 "350_replication_engine"):
        importlib.import_module(f"migrations.standalone.{name}").run(db)
    grants = _Grants()
    branch, a, b, supervisor = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    grants.by_user = {a: set(_CAJERO), b: set(_CAJERO), supervisor: {P.ACCESS}}
    registers = []
    for label in ("Caja 1", "Caja 2"):
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                   (register, branch, label, "ACTIVE", None, _NOW, _NOW))
        db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                   (drawer, branch, register, f"Cajón {label}", "ACTIVE", _NOW, _NOW))
        db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                   (terminal, branch, register, f"POS {label}", "ACTIVE", _NOW, _NOW))
        registers.append((register, drawer, terminal))
    db.commit()
    auth = CashAuthorizationPolicy(grants, _Scopes())
    limit = CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"),
                                    hard_cap=Decimal("5000"))

    def open_shift(cashier, *, index=0, amount="100"):
        register, drawer, terminal = registers[index]
        return OpenCashShiftUseCase(auth, limit).execute(
            db, branch_id=branch, register_id=register, drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=cashier, opening_amount=Decimal(amount), actor_user_id=cashier,
            operation_id=new_uuid()).entity_id

    def reassign(shift_id, *, to, actor=None, reason="Cambio de turno", operation_id=None,
                 in_branch=None):
        return ReassignCashShiftUseCase(auth).execute(
            db, shift_id=shift_id, branch_id=in_branch or branch, new_cashier_user_id=to,
            actor_user_id=actor or supervisor, operation_id=operation_id or new_uuid(),
            reason=reason)

    yield SimpleNamespace(db=db, grants=grants, auth=auth, limit=limit, branch=branch, a=a, b=b,
                          supervisor=supervisor, open=open_shift, reassign=reassign)
    db.close()


def _movement(cash, shift_id, actor):
    return RegisterCashMovementUseCase(cash.auth, cash.limit).execute(
        cash.db, shift_id=shift_id, branch_id=cash.branch,
        movement_type=CashMovementType.MANUAL_INCOME, amount=Decimal("10"), concept="Cambio",
        actor_user_id=actor, operation_id=new_uuid(), reason_code="CHANGE_ADDITION")


def _suspend(cash, shift_id, actor):
    return SuspendCashShiftUseCase(cash.auth).execute(
        cash.db, shift_id=shift_id, branch_id=cash.branch, actor_user_id=actor,
        operation_id=new_uuid(), reason="Motivo")


def _status(cash, shift_id):
    return cash.db.execute("SELECT status FROM cash_shifts WHERE id=?", (shift_id,)).fetchone()[0]


def _assignments(cash, shift_id):
    return cash.db.execute(
        "SELECT cashier_user_id, status, ended_at IS NOT NULL FROM cash_shift_assignments"
        " WHERE shift_id=? ORDER BY assigned_at", (shift_id,)).fetchall()


# ── permisos distintos ─────────────────────────────────────────────────
def test_catalogo_tiene_intervenir_turno_y_movimiento_ajeno_como_permisos_propios():
    assert {P.SHIFT_INTERVENE, P.MOVEMENT_INTERVENE} <= ALL_CASH_PERMISSIONS
    assert len({P.SHIFT_INTERVENE, P.MOVEMENT_INTERVENE, P.SHIFT_FORCE_CLOSE}) == 3


def test_forzar_cierre_ya_no_deja_suspender_ni_mover_efectivo_de_otro(cash):
    shift_id = cash.open(cash.a)
    cash.grants.by_user[cash.supervisor] |= {
        P.SHIFT_SUSPEND, P.MOVEMENT_INCOME, P.SHIFT_FORCE_CLOSE}
    with pytest.raises(CashPermissionDeniedError):
        _suspend(cash, shift_id, cash.supervisor)
    with pytest.raises(CashPermissionDeniedError):
        _movement(cash, shift_id, cash.supervisor)


def test_intervenir_turno_no_concede_mover_efectivo_ajeno(cash):
    shift_id = cash.open(cash.a)
    cash.grants.by_user[cash.supervisor] |= {
        P.SHIFT_SUSPEND, P.MOVEMENT_INCOME, P.SHIFT_INTERVENE}
    with pytest.raises(CashPermissionDeniedError):
        _movement(cash, shift_id, cash.supervisor)
    _suspend(cash, shift_id, cash.supervisor)
    assert _status(cash, shift_id) == "SUSPENDED"


def test_movimiento_ajeno_no_concede_intervenir_el_turno(cash):
    shift_id = cash.open(cash.a)
    cash.grants.by_user[cash.supervisor] |= {
        P.SHIFT_SUSPEND, P.MOVEMENT_INCOME, P.MOVEMENT_INTERVENE}
    assert _movement(cash, shift_id, cash.supervisor)
    with pytest.raises(CashPermissionDeniedError):
        _suspend(cash, shift_id, cash.supervisor)


def test_cerrar_turno_exige_el_permiso_de_cerrar_ademas_de_generar_el_z(cash):
    shift_id = cash.open(cash.a)
    cash.grants.by_user[cash.a].add(P.Z_CUT_GENERATE)
    with pytest.raises(CashPermissionDeniedError, match="turno.cerrar"):
        GenerateZCutUseCase(cash.auth).execute(
            cash.db, shift_id=shift_id, branch_id=cash.branch, actor_user_id=cash.a,
            operation_id=new_uuid())


# ── entrega de turno ───────────────────────────────────────────────────
def test_abrir_turno_deja_la_asignacion_activa(cash):
    shift_id = cash.open(cash.a)
    assert _assignments(cash, shift_id) == [(cash.a, "ACTIVE", 0)]


def test_entregar_el_turno_cambia_de_cajero_con_trazabilidad(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    _movement(cash, shift_id, cash.a)
    result = cash.reassign(shift_id, to=cash.b, reason="Salida de A a comer")
    assert result.entity_id == shift_id
    row = cash.db.execute("SELECT cashier_user_id, version, status FROM cash_shifts WHERE id=?",
                          (shift_id,)).fetchone()
    assert row == (cash.b, 2, "OPEN")
    assert _assignments(cash, shift_id) == [(cash.a, "REASSIGNED", 1), (cash.b, "ACTIVE", 0)]
    # El responsable original de cada movimiento no se reescribe.
    recorded = {r[0] for r in cash.db.execute(
        "SELECT recorded_by FROM cash_ledger_entries WHERE shift_id=?", (shift_id,))}
    assert recorded == {cash.a}
    audit = cash.db.execute(
        "SELECT actor_user_id, reason FROM cash_audit_log WHERE action='CASH_SHIFT_REASSIGNED'"
    ).fetchone()
    assert audit == (cash.supervisor, "Salida de A a comer")
    payload = json.loads(cash.db.execute(
        "SELECT payload_json FROM cash_outbox WHERE event_name='CASH_SHIFT_REASSIGNED'"
    ).fetchone()[0])
    event = payload.get("payload") or payload
    assert (event["previous_cashier_user_id"], event["cashier_user_id"]) == (cash.a, cash.b)


def test_tras_la_entrega_el_turno_es_de_quien_lo_recibe(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    cash.reassign(shift_id, to=cash.b)
    client = SalesCashEffectsClient()
    assert client.require_open_shift(cash.db, branch_id=cash.branch,
                                     cashier_user_id=cash.b) == shift_id
    assert client.open_shift_problem(cash.db, branch_id=cash.branch,
                                     cashier_user_id=cash.a) is not None
    assert cash.open(cash.a, index=1)          # A queda libre para abrir otro


def test_un_turno_suspendido_se_puede_entregar_y_sigue_suspendido(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    _suspend(cash, shift_id, cash.a)
    cash.reassign(shift_id, to=cash.b)
    assert _status(cash, shift_id) == "SUSPENDED"


def test_entregar_exige_el_permiso_de_reasignar(cash):
    shift_id = cash.open(cash.a)
    with pytest.raises(CashPermissionDeniedError):
        cash.reassign(shift_id, to=cash.b, actor=cash.a)
    assert _assignments(cash, shift_id) == [(cash.a, "ACTIVE", 0)]


def test_quien_recibe_debe_poder_abrir_turno_en_la_sucursal(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    cash.grants.by_user[cash.b].discard(P.SHIFT_OPEN)
    shift_id = cash.open(cash.a)
    with pytest.raises(CashPermissionDeniedError):
        cash.reassign(shift_id, to=cash.b)


def test_entregar_exige_motivo(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    with pytest.raises(CashInvalidStateError, match="motivo"):
        cash.reassign(shift_id, to=cash.b, reason="   ")


def test_quien_recibe_no_puede_tener_otro_turno_activo(cash):
    """Regla vigente: turnos incompatibles por cajero (2026-11-02)."""
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a, index=0)
    cash.open(cash.b, index=1)
    with pytest.raises(CashInvalidStateError, match="ya tiene un turno activo"):
        cash.reassign(shift_id, to=cash.b)
    assert cash.db.execute("SELECT cashier_user_id FROM cash_shifts WHERE id=?",
                           (shift_id,)).fetchone()[0] == cash.a


def test_un_turno_en_cierre_no_se_entrega(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    BeginCashShiftClosingUseCase(cash.auth).execute(
        cash.db, shift_id=shift_id, branch_id=cash.branch, actor_user_id=cash.a,
        operation_id=new_uuid())
    with pytest.raises(CashInvalidStateError):
        cash.reassign(shift_id, to=cash.b)


def test_entregar_a_uno_mismo_no_es_entrega(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    with pytest.raises(CashInvalidStateError):
        cash.reassign(shift_id, to=cash.a)


def test_reintentar_la_entrega_es_una_sola_operacion(cash):
    cash.grants.by_user[cash.supervisor].add(P.SHIFT_REASSIGN)
    shift_id = cash.open(cash.a)
    operation_id = new_uuid()
    cash.reassign(shift_id, to=cash.b, operation_id=operation_id)
    again = cash.reassign(shift_id, to=cash.b, operation_id=operation_id)
    assert again.entity_id == shift_id and again.idempotent
    assert len(_assignments(cash, shift_id)) == 2


# ── revisar el Corte Z ─────────────────────────────────────────────────
def _final_cut(cash, shift_id, actor):
    cut_id, now = new_uuid(), _NOW
    cash.db.execute("PRAGMA foreign_keys=OFF")   # el arqueo no importa aquí
    cash.db.execute(
        """INSERT INTO cash_cuts (id,shift_id,branch_id,cut_type,document_number,snapshot_json,
        generated_by,expected_cash,counted_cash,difference,blind_count_id,operation_id,is_final,
        generated_at) VALUES (?,?,?,'Z','Z-1','{}',?,'100','100','0',?,?,1,?)""",
        (cut_id, shift_id, cash.branch, actor, new_uuid(), new_uuid(), now))
    cash.db.commit()
    return cut_id


def _review(cash, cut_id, actor, operation_id=None, note="Cuadra con el conteo"):
    return ReviewZCutUseCase(cash.auth).execute(
        cash.db, cut_id=cut_id, branch_id=cash.branch, actor_user_id=actor,
        operation_id=operation_id or new_uuid(), note=note)


def test_revisar_el_z_exige_su_permiso_y_queda_auditado(cash):
    cut_id = _final_cut(cash, cash.open(cash.a), cash.a)
    with pytest.raises(CashPermissionDeniedError):
        _review(cash, cut_id, cash.supervisor)
    cash.grants.by_user[cash.supervisor].add(P.Z_CUT_REVIEW)
    result = _review(cash, cut_id, cash.supervisor)
    assert result.entity_id == cut_id and not result.idempotent
    assert cash.db.execute(
        "SELECT actor_user_id, reason FROM cash_audit_log WHERE action='CASH_Z_CUT_REVIEWED'"
    ).fetchone() == (cash.supervisor, "Cuadra con el conteo")


def test_el_z_se_revisa_una_sola_vez(cash):
    cash.grants.by_user[cash.supervisor].add(P.Z_CUT_REVIEW)
    cut_id = _final_cut(cash, cash.open(cash.a), cash.a)
    _review(cash, cut_id, cash.supervisor)
    assert _review(cash, cut_id, cash.supervisor).idempotent
    assert cash.db.execute(
        "SELECT COUNT(*) FROM cash_audit_log WHERE action='CASH_Z_CUT_REVIEWED'"
    ).fetchone()[0] == 1


# ── migración 359 ──────────────────────────────────────────────────────
def _roles_db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT)")
    db.execute("CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT,"
               " accion TEXT, permitido INTEGER)")
    return db


def _grant(db, role_id, *actions):
    for action in actions:
        db.execute("INSERT INTO rol_permisos VALUES (?,?,?,?,1)",
                   (new_uuid(), role_id, "CAJA", action))


def _actions(db, role_id):
    return {row[0] for row in db.execute(
        "SELECT accion FROM rol_permisos WHERE rol_id=? AND modulo='CAJA'", (role_id,))}


def test_359_conserva_lo_que_cada_rol_ya_podia_hacer():
    db = _roles_db()
    supervisor, generador, cajero = new_uuid(), new_uuid(), new_uuid()
    for role_id, name in ((supervisor, "supervisor x"), (generador, "cortes"),
                          (cajero, "cajero x")):
        db.execute("INSERT INTO roles VALUES (?,?)", (role_id, name))
    _grant(db, supervisor, "turno.forzar_cierre")
    _grant(db, generador, "corte_z.generar")
    _grant(db, cajero, "turno.ver")
    migration = importlib.import_module("migrations.standalone.359_cash_permissions_split")
    migration.run(db)
    migration.run(db)   # idempotente
    assert _actions(db, supervisor) == {"turno.forzar_cierre", "turno.intervenir",
                                        "movimiento.intervenir"}
    assert _actions(db, generador) == {"corte_z.generar", "turno.cerrar"}
    assert _actions(db, cajero) == {"turno.ver"}


def test_359_da_asignacion_activa_a_los_turnos_vivos(cash):
    shift_id = cash.open(cash.a)
    cash.db.execute("DELETE FROM cash_shift_assignments")
    cash.db.commit()
    migration = importlib.import_module("migrations.standalone.359_cash_permissions_split")
    migration.run(cash.db)
    migration.run(cash.db)
    assert _assignments(cash, shift_id) == [(cash.a, "ACTIVE", 0)]


# ── pantalla ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test"])


def test_dialogos_de_entrega_y_revision_exigen_el_motivo(qapp):
    from frontend.desktop.modules.cash_register.cash_register_dialogs import (
        CashShiftHandoverDialog,
        ReviewZCutDialog,
    )

    shift = SimpleNamespace(register_name="Caja 1", cashier_name="Ana", status="OPEN")
    users = [SimpleNamespace(id="u-1", name="Beto")]
    dialog = CashShiftHandoverDialog(None, shift=shift, users=users)
    dialog.accept()
    assert dialog.result() != dialog.Accepted
    dialog.reason.setPlainText("Cambio de cajero")
    dialog.accept()
    assert dialog.result() == dialog.Accepted
    assert dialog.result_value().new_cashier_user_id == "u-1"
    review = ReviewZCutDialog(None, document=SimpleNamespace(document_number="Z-1"))
    review.accept()
    assert review.result() != review.Accepted
