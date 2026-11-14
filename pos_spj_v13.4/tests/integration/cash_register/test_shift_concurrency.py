"""SDLC-ARQ-SHIFT-004: concurrencia e idempotencia de las transiciones de turno.

Dos conexiones reales sobre una base en disco (WAL, autocommit y `busy_timeout`
como `backend/infrastructure/db/connection.py`), porque en una sola conexión la
carrera no existe. Aceptación §12/§15 del documento de arquitectura: "dos
usuarios confirman/cierran simultáneamente → invariantes respetadas" y "doble
clic, reintentos, timeout → una sola operación lógica".
"""
from __future__ import annotations

import importlib
import sqlite3
import threading
from decimal import Decimal

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase,
    OpenCashShiftUseCase,
    ResumeCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.domain.cash_register.exceptions import (
    CashDuplicateOperationError,
    CashInvalidStateError,
    CashShiftConflictError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy
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


class _Env:
    def __init__(self, path) -> None:
        self.path = str(path)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.branch, self.cashier = new_uuid(), new_uuid()
        self.other_cashier = new_uuid()
        self.devices: list[tuple[str, str, str]] = []
        db = self.connect()
        for name in ("176_cash_register_configuration_schema",
                     "175_cash_register_bounded_context_schema",
                     "350_replication_engine"):
            importlib.import_module(f"migrations.standalone.{name}").run(db)
        for label in ("Caja 1", "Caja 2"):
            register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
            db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                       (register, self.branch, label, "ACTIVE", None, _NOW, _NOW))
            db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                       (drawer, self.branch, register, f"Cajón {label}", "ACTIVE", _NOW, _NOW))
            db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                       (terminal, self.branch, register, f"POS {label}", "ACTIVE", _NOW, _NOW))
            self.devices.append((register, drawer, terminal))
        if db.in_transaction:
            db.commit()
        db.close()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None,
                               check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def open_shift(self, conn, *, cashier=None, operation_id=None, index=0, amount="100"):
        register, drawer, terminal = self.devices[index]
        cashier = cashier or self.cashier
        return OpenCashShiftUseCase(self.auth, self.limit).execute(
            conn, branch_id=self.branch, register_id=register, drawer_id=drawer,
            terminal_id=terminal, cashier_user_id=cashier, opening_amount=Decimal(amount),
            actor_user_id=cashier, operation_id=operation_id or new_uuid())

    def transition(self, conn, use_case, shift_id, reason="Motivo"):
        return use_case(self.auth).execute(
            conn, shift_id=shift_id, branch_id=self.branch, actor_user_id=self.cashier,
            operation_id=new_uuid(), reason=reason)

    def race(self, *actions):
        """Corre cada acción en su hilo y con su conexión, soltadas a la vez.
        Devuelve lo que devolvió o lanzó cada una."""
        barrier = threading.Barrier(len(actions))
        outcomes: list[object] = [None] * len(actions)

        def run(position, action):
            conn = self.connect()
            try:
                barrier.wait(timeout=15)
                outcomes[position] = action(conn)
            except Exception as exc:  # noqa: BLE001 - se inspecciona en la prueba
                outcomes[position] = exc
            finally:
                conn.close()

        threads = [threading.Thread(target=run, args=(position, action))
                   for position, action in enumerate(actions)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert not any(thread.is_alive() for thread in threads)
        return outcomes


@pytest.fixture
def env(tmp_path):
    return _Env(tmp_path / "cash.db")


def _shift_row(conn, shift_id):
    return conn.execute("SELECT status, version FROM cash_shifts WHERE id=?",
                        (shift_id,)).fetchone()


# ── compare-and-set ────────────────────────────────────────────────────
def test_cada_transicion_incrementa_la_version(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    assert _shift_row(db, shift_id) == ("OPEN", 1)
    env.transition(db, SuspendCashShiftUseCase, shift_id)
    assert _shift_row(db, shift_id) == ("SUSPENDED", 2)
    env.transition(db, ResumeCashShiftUseCase, shift_id)
    assert _shift_row(db, shift_id) == ("OPEN", 3)
    env.transition(db, BeginCashShiftClosingUseCase, shift_id)
    assert _shift_row(db, shift_id) == ("CLOSING", 4)


def test_quien_leyo_una_version_vieja_recibe_conflicto_y_no_escribe(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    env.transition(db, SuspendCashShiftUseCase, shift_id)   # versión 2, SUSPENDED
    with pytest.raises(CashShiftConflictError):
        with CashRegisterUnitOfWork(db) as uow:
            uow.shifts.set_lifecycle(shift_id=shift_id, status="CLOSING",
                                     expected_status="OPEN", expected_version=1)
    assert _shift_row(db, shift_id) == ("SUSPENDED", 2)


def test_la_misma_version_con_otro_estado_tambien_es_conflicto(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    with pytest.raises(CashShiftConflictError):
        with CashRegisterUnitOfWork(db) as uow:
            uow.shifts.set_lifecycle(shift_id=shift_id, status="OPEN",
                                     expected_status="SUSPENDED", expected_version=1)
    assert _shift_row(db, shift_id) == ("OPEN", 1)


def test_conflicto_es_un_error_de_estado_para_los_except_existentes():
    assert issubclass(CashShiftConflictError, CashInvalidStateError)


# ── dos conexiones a la vez ────────────────────────────────────────────
def test_suspender_y_preparar_cierre_a_la_vez_sale_un_solo_ganador(env):
    for _ in range(5):
        db = env.connect()
        cashier = new_uuid()
        shift_id = env.open_shift(db, cashier=cashier).entity_id
        outcomes = env.race(
            lambda conn: _transition_as(env, conn, SuspendCashShiftUseCase, shift_id, cashier),
            lambda conn: _transition_as(env, conn, BeginCashShiftClosingUseCase, shift_id, cashier))
        winners = [item for item in outcomes if not isinstance(item, Exception)]
        losers = [item for item in outcomes if isinstance(item, Exception)]
        assert len(winners) == 1, outcomes
        assert len(losers) == 1 and isinstance(losers[0], CashInvalidStateError), outcomes
        status, version = _shift_row(db, shift_id)
        assert status in {"SUSPENDED", "CLOSING"}
        assert version == 2
        _release(env, db, shift_id, status, cashier)
        db.close()


def test_reanudar_y_suspender_a_la_vez_deja_un_estado_valido(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    env.transition(db, SuspendCashShiftUseCase, shift_id)   # versión 2
    outcomes = env.race(
        lambda conn: env.transition(conn, ResumeCashShiftUseCase, shift_id),
        lambda conn: env.transition(conn, BeginCashShiftClosingUseCase, shift_id))
    failures = [item for item in outcomes if isinstance(item, Exception)]
    assert all(isinstance(item, CashInvalidStateError) for item in failures), outcomes
    status, version = _shift_row(db, shift_id)
    assert CashShiftLifecyclePolicy.is_active(status)
    assert status in {"OPEN", "CLOSING"}
    assert version == 2 + len(outcomes) - len(failures)


def test_doble_suspension_simultanea_aplica_una_vez(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    outcomes = env.race(
        lambda conn: env.transition(conn, SuspendCashShiftUseCase, shift_id),
        lambda conn: env.transition(conn, SuspendCashShiftUseCase, shift_id))
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1, outcomes
    assert _shift_row(db, shift_id) == ("SUSPENDED", 2)
    events = db.execute("SELECT COUNT(*) FROM cash_outbox WHERE event_name='CASH_SHIFT_SUSPENDED'"
                        ).fetchone()[0]
    assert events == 1


def test_dos_aperturas_del_mismo_cajero_dejan_un_turno(env):
    """Regla vigente (decisión 2026-11-02): turnos incompatibles por cajero."""
    db = env.connect()
    outcomes = env.race(
        lambda conn: env.open_shift(conn, index=0),
        lambda conn: env.open_shift(conn, index=1))
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1, outcomes
    failure = next(item for item in outcomes if isinstance(item, Exception))
    assert isinstance(failure, CashInvalidStateError), outcomes
    assert "ya tiene un turno activo" in str(failure)
    assert db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0] == 1


# ── apertura idempotente ───────────────────────────────────────────────
def test_reintentar_la_apertura_devuelve_el_turno_original(env):
    db = env.connect()
    operation_id = new_uuid()
    first = env.open_shift(db, operation_id=operation_id)
    again = env.open_shift(db, operation_id=operation_id)
    assert again.entity_id == first.entity_id
    assert db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM cash_ledger_entries").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM cash_outbox WHERE event_name='CASH_SHIFT_OPENED'"
                      ).fetchone()[0] == 1


def test_reintento_tras_cambiar_de_estado_devuelve_el_mismo_turno(env):
    db = env.connect()
    operation_id = new_uuid()
    shift_id = env.open_shift(db, operation_id=operation_id).entity_id
    env.transition(db, SuspendCashShiftUseCase, shift_id)
    assert env.open_shift(db, operation_id=operation_id).entity_id == shift_id
    assert _shift_row(db, shift_id) == ("SUSPENDED", 2)


def test_misma_operacion_con_otros_datos_no_se_confunde_con_un_reintento(env):
    db = env.connect()
    operation_id = new_uuid()
    env.open_shift(db, operation_id=operation_id)
    with pytest.raises(CashDuplicateOperationError):
        env.open_shift(db, operation_id=operation_id, amount="250")
    with pytest.raises(CashDuplicateOperationError):
        env.open_shift(db, operation_id=operation_id, cashier=env.other_cashier, index=1)
    assert db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0] == 1


def test_doble_clic_de_apertura_simultaneo_es_una_sola_operacion(env):
    db = env.connect()
    operation_id = new_uuid()
    outcomes = env.race(
        lambda conn: env.open_shift(conn, operation_id=operation_id),
        lambda conn: env.open_shift(conn, operation_id=operation_id))
    assert not any(isinstance(item, Exception) for item in outcomes), outcomes
    assert outcomes[0].entity_id == outcomes[1].entity_id
    assert db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM cash_ledger_entries").fetchone()[0] == 1


# ── migración ──────────────────────────────────────────────────────────
def test_358_agrega_la_version_a_una_base_existente_sin_tocar_los_turnos(env):
    db = env.connect()
    shift_id = env.open_shift(db).entity_id
    env.transition(db, SuspendCashShiftUseCase, shift_id)
    db.execute("ALTER TABLE cash_shifts DROP COLUMN version")
    migration = importlib.import_module("migrations.standalone.358_cash_shift_version")
    migration.run(db)
    migration.run(db)   # idempotente
    assert _shift_row(db, shift_id) == ("SUSPENDED", 1)
    env.transition(db, ResumeCashShiftUseCase, shift_id)
    assert _shift_row(db, shift_id) == ("OPEN", 2)


# ── ayudas ─────────────────────────────────────────────────────────────
def _transition_as(env, conn, use_case, shift_id, actor):
    return use_case(env.auth).execute(
        conn, shift_id=shift_id, branch_id=env.branch, actor_user_id=actor,
        operation_id=new_uuid(), reason="Motivo")


def _release(env, db, shift_id, status, cashier):
    """Libera caja, cajón y terminal para la siguiente vuelta de la carrera."""
    db.execute("UPDATE cash_shifts SET status='CANCELLED' WHERE id=?", (shift_id,))
