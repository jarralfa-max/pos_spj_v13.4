"""CASH-26 — re-auditoría de Caja sobre una copia de la base real (2026-10-07).

Cada prueba fija un hallazgo medido en la app viva, donde los 306 tests
existentes pasaban pero un turno no podía completarse:

* 306: ningún rol (salvo el bypass de dueño/admin) tenía las acciones de Caja;
  un cajero no podía abrir turno y por tanto no podía vender.
* 307: denominaciones, motivos, límites y tolerancias nacían vacíos → sin conteo
  confirmable, sin Corte Z, sin movimientos.
* 308: resolver una diferencia exigía tres personas distintas.
* Folio del Corte X derivado del UUID: el segundo corte del minuto chocaba.
* Los límites se leían al abrir Caja; uno nuevo no aplicaba.
* Motivos y tolerancias no tenían escritor; la configuración era texto libre.
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.configuration_use_cases import (
    ConfigureCashRegisterUseCase,
    DeactivateCashConfigurationUseCase,
    build_cash_catalog_command,
)
from backend.application.cash_register.ledger_use_cases import RegisterCashMovementUseCase
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.cash_register.x_cut_use_cases import GenerateXCutUseCase
from backend.domain.cash_register.entities import CashDifference
from backend.domain.cash_register.enums import CashMovementType
from backend.domain.cash_register.exceptions import (
    CashLimitExceededError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.operation_limits import (
    EffectiveCashLimitPolicy,
)
from backend.shared.ids import new_uuid

_175 = importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema")
_176 = importlib.import_module("migrations.standalone.176_cash_register_configuration_schema")
_306 = importlib.import_module("migrations.standalone.306_seed_cash_register_role_permissions")
_307 = importlib.import_module("migrations.standalone.307_seed_cash_register_catalogs")
_308 = importlib.import_module("migrations.standalone.308_cash_difference_two_person_rule")


class _AllPermissions:
    def has_permission(self, user_id, permission_code):
        return permission_code in ALL_CASH_PERMISSIONS


class _AllScopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


AUTH = CashAuthorizationPolicy(_AllPermissions(), _AllScopes())


# ── 306: permisos ───────────────────────────────────────────────────────────
@pytest.fixture
def roles_db():
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT);"
        "CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT, accion TEXT,"
        " permitido INTEGER, UNIQUE(rol_id, modulo, accion));")
    for rol in ("system_owner", "admin", "gerente", "cajero", "solo_lectura", "almacen"):
        c.execute("INSERT INTO roles VALUES (?,?)", (new_uuid(), rol))
    # Lo que tenía la base real: códigos gruesos de la Caja vieja.
    cajero = c.execute("SELECT id FROM roles WHERE nombre='cajero'").fetchone()[0]
    for accion in ("ver", "crear", "editar", "eliminar"):
        c.execute("INSERT INTO rol_permisos VALUES (?,?,?,?,1)", (new_uuid(), cajero, "CAJA", accion))
    c.commit()
    yield c
    c.close()


def _caja(conn, rol):
    return {r[0] for r in conn.execute(
        "SELECT rp.accion FROM rol_permisos rp JOIN roles r ON r.id=rp.rol_id"
        " WHERE r.nombre=? AND rp.modulo='CAJA'", (rol,))}


class TestSeed306:
    def test_transcription_matches_cash_permissions(self):
        assert {f"CAJA.{a}" for a in _306._TODAS} == ALL_CASH_PERMISSIONS

    def test_owner_and_admin_get_everything(self, roles_db):
        _306.run(roles_db)
        for rol in ("system_owner", "admin"):
            assert _caja(roles_db, rol) == set(_306._TODAS)

    def test_cashier_operates_own_shift_but_not_sensitive_actions(self, roles_db):
        _306.run(roles_db)
        cajero = _caja(roles_db, "cajero")
        assert {"turno.abrir", "movimiento.ingreso", "movimiento.safe_drop", "conteo.confirmar",
                "corte_x.generar", "corte_z.generar", "diferencia.explicar",
                "cajon.abrir"} <= cajero
        assert not ({"diferencia.revisar", "diferencia.resolver", "movimiento.reversar",
                     "configuracion.editar", "conteo.ver_esperado",
                     "movimiento.autorizar_exceso"} & cajero)

    def test_manager_supervises_but_does_not_define_installation(self, roles_db):
        _306.run(roles_db)
        gerente = _caja(roles_db, "gerente")
        assert {"diferencia.revisar", "diferencia.resolver", "movimiento.autorizar_exceso",
                "entrega.recibir", "conteo.ver_esperado"} <= gerente
        assert not ({"configuracion.editar", "caja.crear", "hardware.gestionar",
                     "whatsapp.gestionar", "diferencia.castigar"} & gerente)

    def test_legacy_coarse_codes_are_removed_and_run_is_idempotent(self, roles_db):
        _306.run(roles_db)
        _306.run(roles_db)
        assert not ({"crear", "editar", "eliminar"} & _caja(roles_db, "cajero"))
        assert _caja(roles_db, "almacen") == set()
        total = roles_db.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0]
        _306.run(roles_db)
        assert roles_db.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0] == total


# ── 307/308 + casos de uso sobre el esquema real ───────────────────────────
@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    _175.run(c)
    _176.run(c)
    c.execute("CREATE TABLE usuarios (id TEXT PRIMARY KEY, rol TEXT)")
    c.execute("INSERT INTO usuarios VALUES (?, 'system_owner')", (new_uuid(),))
    c.commit()
    yield c
    c.close()


def _shift(conn, *, opening=Decimal("500")):
    branch = new_uuid()
    register, drawer, terminal, cashier = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    now = "2026-08-03T00:00:00+00:00"
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch, "Caja", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch, register, "Cajon", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch, register, "POS", "ACTIVE", now, now))
    conn.commit()
    shift = OpenCashShiftUseCase(AUTH, EffectiveCashLimitPolicy(conn, "OPENING_FLOAT")).execute(
        conn, branch_id=branch, register_id=register, drawer_id=drawer, terminal_id=terminal,
        cashier_user_id=cashier, opening_amount=opening, actor_user_id=cashier,
        operation_id=new_uuid()).entity_id
    return branch, cashier, shift


class TestSeed307:
    def test_seeds_the_catalogs_a_shift_needs_to_close(self, db):
        _307.run(db)
        valores = {Decimal(r[0]) for r in db.execute(
            "SELECT denomination_value FROM cash_denominations WHERE currency_code='MXN'")}
        assert {Decimal("1000"), Decimal("500"), Decimal("20"), Decimal("0.50")} <= valores
        limites = {r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT operation_type, approval_threshold, hard_cap FROM cash_operation_limits")}
        assert limites["OPENING_FLOAT"] == ("2000", "5000")
        assert limites["MANUAL_MOVEMENT"] == ("1000", "5000")
        assert limites["SAFE_DROP"] == ("10000", "50000")
        assert db.execute(
            "SELECT tolerance_amount, critical_threshold, recurrence_window_days,"
            " recurrence_threshold FROM cash_difference_policies").fetchone() == ("10", "200", 30, 3)
        tipos = {r[0] for r in db.execute("SELECT DISTINCT movement_type FROM cash_movement_reasons")}
        assert tipos == {"MANUAL_INCOME", "MANUAL_WITHDRAWAL", "SAFE_DROP"}

    def test_never_overwrites_what_the_installation_already_captured(self, db):
        ConfigureCashRegisterUseCase(AUTH).execute_typed(
            db, command=build_cash_catalog_command("limits", {
                "operation_type": "MANUAL_MOVEMENT", "approval_threshold": Decimal("50"),
                "hard_cap": Decimal("100")}),
            actor_user_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())
        _307.run(db)
        _307.run(db)
        assert db.execute("SELECT approval_threshold, hard_cap FROM cash_operation_limits"
                          " WHERE operation_type='MANUAL_MOVEMENT'").fetchall() == [("50", "100")]
        assert db.execute("SELECT COUNT(*) FROM cash_denominations").fetchone()[0] == len(
            _307._DENOMINACIONES)


class TestTwoPersonDifferenceRule308:
    def test_domain_rule_lets_reviewer_resolve_but_never_the_responsible(self):
        cashier, manager = new_uuid(), new_uuid()
        with pytest.raises(CashSegregationOfDutiesError):
            CashDifference.require_independent(cashier, responsible_user_id=cashier,
                                               explained_by=cashier, action="resolución")
        CashDifference.require_independent(manager, responsible_user_id=cashier,
                                           explained_by=cashier, action="resolución")

    def test_rebuild_preserves_rows_and_allows_two_people(self):
        c = sqlite3.connect(":memory:")
        viejo = _175.DDL
        # Base existente: la tabla con la regla de TRES personas (con ella, quien
        # revisó NO podía resolver: el UPDATE de abajo fallaba).
        legacy_ddl = [
            sql.replace("reviewed_by<>responsible_user_id", "reviewed_by<>detected_by")
               .replace("resolved_by<>responsible_user_id AND resolved_by<>explained_by)",
                        "resolved_by<>detected_by AND resolved_by<>explained_by AND resolved_by<>reviewed_by)")
            for sql in viejo
        ]
        for sql in legacy_ddl:
            c.execute(sql)
        branch, cashier, manager = new_uuid(), new_uuid(), new_uuid()
        register, drawer, terminal, shift, cut, count = (new_uuid() for _ in range(6))
        now = "2026-08-03T00:00:00+00:00"
        c.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                  (register, branch, "Caja", "ACTIVE", None, now, now))
        c.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                  (drawer, branch, register, "C", "ACTIVE", now, now))
        c.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                  (terminal, branch, register, "T", "ACTIVE", now, now))
        c.execute("INSERT INTO cash_shifts (id,branch_id,register_id,drawer_id,terminal_id,"
                  "cashier_user_id,opening_amount,opening_operation_id,status,opened_at)"
                  " VALUES (?,?,?,?,?,?,'0',?,'CLOSING',?)",
                  (shift, branch, register, drawer, terminal, cashier, new_uuid(), now))
        c.execute("INSERT INTO cash_cuts (id,shift_id,branch_id,cut_type,document_number,"
                  "generated_by,expected_cash,counted_cash,difference,blind_count_id,operation_id,"
                  "is_final,generated_at) VALUES (?,?,?,'Z','Z-1',?,'0','5','5',?,?,1,?)",
                  (cut, shift, branch, manager, count, new_uuid(), now))
        diff = new_uuid()
        c.execute("INSERT INTO cash_differences (id,shift_id,z_cut_id,branch_id,expected_amount,"
                  "counted_amount,amount,detected_by,operation_id,responsible_user_id,"
                  "classification,severity,tolerance_amount,recurrence_count,status,explanation,"
                  "explained_by,reviewed_by) VALUES (?,?,?,?,'0','5','5',?,?,?,'OVERAGE','REVIEW',"
                  "'1',1,'UNDER_REVIEW','x',?,?)",
                  (diff, shift, cut, branch, cashier, new_uuid(), cashier, cashier, manager))
        c.commit()
        _308.run(c)
        _308.run(c)
        assert c.execute("SELECT COUNT(*) FROM cash_differences").fetchone()[0] == 1
        c.execute("UPDATE cash_differences SET resolved_by=?, status='RESOLVED' WHERE id=?",
                  (manager, diff))
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE cash_differences SET resolved_by=? WHERE id=?", (cashier, diff))
        c.close()



# ── folios, límites vigentes, configuración tipada ─────────────────────────
class TestXCutFolio:
    def test_two_x_cuts_in_the_same_minute_do_not_collide(self, db):
        branch, cashier, shift = _shift(db, opening=Decimal("0"))
        first = GenerateXCutUseCase(AUTH).execute(
            db, shift_id=shift, branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())
        second = GenerateXCutUseCase(AUTH).execute(
            db, shift_id=shift, branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())
        assert first.document_number != second.document_number


class TestEffectiveLimits:
    def test_a_limit_captured_after_the_screen_opened_applies_immediately(self, db):
        _307.run(db)
        policy = EffectiveCashLimitPolicy(db, "MANUAL_MOVEMENT")
        assert policy.hard_cap == Decimal("5000")
        ConfigureCashRegisterUseCase(AUTH).execute_typed(
            db, command=build_cash_catalog_command("limits", {
                "operation_type": "MANUAL_MOVEMENT", "approval_threshold": Decimal("10"),
                "hard_cap": Decimal("20")}),
            actor_user_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())
        assert policy.hard_cap == Decimal("20")
        with pytest.raises(CashLimitExceededError):
            policy.require_operable(Decimal("21"))
        vigentes = db.execute("SELECT COUNT(*) FROM cash_operation_limits WHERE"
                              " operation_type='MANUAL_MOVEMENT' AND effective_to IS NULL")
        assert vigentes.fetchone()[0] == 1


class TestTypedConfiguration:
    def _configure(self, db, section, fields):
        return ConfigureCashRegisterUseCase(AUTH).execute_typed(
            db, command=build_cash_catalog_command(section, fields),
            actor_user_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())

    def test_reasons_and_tolerances_now_have_a_writer(self, db):
        self._configure(db, "reasons", {
            "movement_type": "MANUAL_INCOME", "code": "dotacion", "display_name": "Dotacion",
            "requires_authorization": True})
        self._configure(db, "tolerances", {
            "tolerance": Decimal("5"), "critical_threshold": Decimal("50"),
            "recurrence_window_days": 7, "recurrence_threshold": 2, "channels": ("IN_APP",)})
        assert db.execute("SELECT code, requires_authorization FROM cash_movement_reasons"
                          ).fetchall() == [("DOTACION", 1)]
        assert db.execute("SELECT tolerance_amount, critical_threshold FROM"
                          " cash_difference_policies").fetchall() == [("5", "50")]

    def test_new_denomination_replaces_the_same_value_instead_of_counting_twice(self, db):
        fields = {"currency_code": "MXN", "value": Decimal("500"), "display_name": "Billete",
                  "sort_order": 0}
        self._configure(db, "denominations", fields)
        db.execute("UPDATE cash_denominations SET effective_from='2026-01-01T00:00:00+00:00'")
        self._configure(db, "denominations", {**fields, "display_name": "Billete $500"})
        assert db.execute("SELECT COUNT(*) FROM cash_denominations WHERE effective_to IS NULL"
                          ).fetchone()[0] == 1

    def test_deactivate_closes_validity_and_keeps_history(self, db):
        _307.run(db)
        reason_id = db.execute("SELECT id FROM cash_movement_reasons WHERE code='SCHEDULED'"
                               ).fetchone()[0]
        DeactivateCashConfigurationUseCase(AUTH).execute(
            db, section="reasons", row_id=reason_id, actor_user_id=new_uuid(),
            branch_id=new_uuid(), operation_id=new_uuid())
        assert db.execute("SELECT effective_to IS NOT NULL FROM cash_movement_reasons WHERE id=?",
                          (reason_id,)).fetchone()[0] == 1
        with pytest.raises(ValueError):
            DeactivateCashConfigurationUseCase(AUTH).execute(
                db, section="reasons", row_id=reason_id, actor_user_id=new_uuid(),
                branch_id=new_uuid(), operation_id=new_uuid())

    def test_supplier_payment_cannot_be_a_cash_withdrawal(self, db):
        _307.run(db)
        branch, cashier, shift = _shift(db)
        with pytest.raises(Exception):
            RegisterCashMovementUseCase(AUTH, EffectiveCashLimitPolicy(db, "MANUAL_MOVEMENT")).execute(
                db, shift_id=shift, branch_id=branch,
                movement_type=CashMovementType.MANUAL_WITHDRAWAL, amount=Decimal("100"),
                concept="Pago a proveedor", actor_user_id=cashier, operation_id=new_uuid())
        assert db.execute("SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type="
                          "'MANUAL_WITHDRAWAL'").fetchone()[0] == 0
