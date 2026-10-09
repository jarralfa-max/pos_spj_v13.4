"""CASH-26 — un turno completo de punta a punta con DOS usuarios reales.

Re-auditoría del 2026-10-07: en la app viva un turno no podía completarse
(permisos sin sembrar, catálogos vacíos, autorización en caliente muerta,
folio de Corte X repetido). Este flujo usa la composición REAL de la pantalla
(`build_cash_register_presenter`), sesiones con los permisos que `rol_permisos`
da a cada rol, y los catálogos que siembra la migración 307:

  cajero abre turno → ingreso → retiro mayor al umbral autorizado con la CLAVE
  del gerente → retiro a bóveda → entrega de valores que recibe OTRA persona →
  dos Cortes X → cierre → conteo ciego → Corte Z con diferencia → el cajero la
  explica → el dueño la revisa y la resuelve.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.security.permission_query_service import PermissionQueryService
from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError,
    CashSegregationOfDutiesError,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

OWNER_PASSWORD = "Correct-Horse-9!"
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Root:
    def __init__(self, conn, session):
        self.db, self.session = conn, session


@pytest.fixture
def conn():
    c = make_db()
    ProvisionInstallationUseCase(
        c, installation_repository=SqliteInstallationRepository(c),
        recovery_code_repository=SqliteRecoveryCodeRepository(c),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", branch_name="Centro", owner_username="duena",
              workstation_name="Caja 1", owner_password=OWNER_PASSWORD,
              owner_full_name="Duena", now=T0)
    for name in ("175_cash_register_bounded_context_schema",
                 "176_cash_register_configuration_schema",
                 "306_seed_cash_register_role_permissions",
                 "307_seed_cash_register_catalogs",
                 "308_cash_difference_two_person_rule"):
        importlib.import_module(f"migrations.standalone.{name}").run(c)
    c.commit()
    yield c
    c.close()


def _session(conn, user_id, branch_id, role):
    perms = PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(
        user_id, branch_id)
    ctx = ApplicationContext(
        installation_id="", company_id="", branch_id=branch_id, branch_name="Centro",
        assigned_branch_ids=frozenset({branch_id}), workstation_id="ws", workstation_type="",
        user_id=user_id, user_name=role, roles=(role,), permissions=frozenset(perms),
        feature_context=FeatureContext.from_flags_dict({}), session_id=new_uuid())
    return LegacySessionAdapter(ctx)


def test_full_shift_with_cashier_and_owner(conn):
    owner_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    cashier_id = new_uuid()
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
                 " VALUES (?, 'Ana', 'ana', 'x', 'cajero', ?, 1)", (cashier_id, branch_id))
    now = "2026-08-03T00:00:00+00:00"
    register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch_id, "CAJA-01", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch_id, register, "CAJON-01", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch_id, register, "TER-01", "ACTIVE", now, now))
    conn.commit()

    cajero = build_cash_register_presenter(_Root(conn, _session(conn, cashier_id, branch_id,
                                                                "cajero")))
    duena = build_cash_register_presenter(_Root(conn, _session(conn, owner_id, branch_id,
                                                               "system_owner")))

    # 1. Abrir turno con fondo dentro del límite sembrado (≤ $2,000 sin autorización).
    cajero.open_cash_shift(opening_amount=Decimal("1000.00"))
    shift_id = cajero.active_shift_id()

    # 2. Ingreso con motivo del catálogo.
    cajero.register_cash_movement(movement_type="MANUAL_INCOME", amount=Decimal("500.00"),
                                  concept="Dotacion de cambio", reason_code="CHANGE_ADDITION")

    # 3. Retiro mayor al umbral: pide autorizador; una clave mala NO autoriza.
    with pytest.raises(CashAuthorizationRequiredError):
        cajero.register_cash_movement(movement_type="MANUAL_WITHDRAWAL", amount=Decimal("1200.00"),
                                      concept="Operacion", reason_code="AUTHORIZED_OPERATION")
    with pytest.raises(CashAuthorizationRequiredError):
        cajero.resolve_authorizer(username="duena", password="adivinada")
    autoriza = cajero.resolve_authorizer(username="duena", password=OWNER_PASSWORD)
    assert autoriza == owner_id
    cajero.register_cash_movement(movement_type="MANUAL_WITHDRAWAL", amount=Decimal("1200.00"),
                                  concept="Operacion", reason_code="AUTHORIZED_OPERATION",
                                  authorized_by=autoriza)

    # 4. Retiro a bóveda y entrega de valores: entrega el cajero, recibe OTRA persona.
    drop = cajero.register_cash_movement(movement_type="SAFE_DROP", amount=Decimal("100.00"),
                                         concept="Boveda", reason_code="CASH_LIMIT")
    cien = next(d.id for d in cajero.denomination_options() if d.value == Decimal("100"))
    handover = cajero.prepare_cash_handover(safe_drop_entry_id=drop.entity_id,
                                            denominations={cien: 1})
    cajero.deliver_cash_handover(handover_id=handover.entity_id, denominations={cien: 1})
    with pytest.raises(Exception):
        cajero.receive_cash_handover(handover_id=handover.entity_id, denominations={cien: 1})
    duena.receive_cash_handover(handover_id=handover.entity_id, denominations={cien: 1})

    # 5. Dos Cortes X seguidos: folios distintos (antes chocaban dentro del mismo minuto).
    x1 = cajero.generate_x_cut()
    x2 = cajero.generate_x_cut()
    assert x1.document_number != x2.document_number

    # 6. Cierre, conteo ciego con las denominaciones sembradas y Corte Z.
    cajero.begin_cash_shift_closing()
    count = cajero.start_blind_count()
    cincuenta = next(d.id for d in cajero.denomination_options() if d.value == Decimal("50"))
    cajero.capture_blind_count_denomination(count_id=count.entity_id, denomination_id=cien,
                                            quantity=2)
    cajero.capture_blind_count_denomination(count_id=count.entity_id, denomination_id=cincuenta,
                                            quantity=1)
    cajero.confirm_blind_count(count_id=count.entity_id)
    z = cajero.generate_z_cut()

    shift = conn.execute("SELECT status, z_cut_id FROM cash_shifts WHERE id=?",
                         (shift_id,)).fetchone()
    assert tuple(shift) == ("CLOSED", z.entity_id)
    # Esperado: 1000 + 500 - 1200 - 100 = 200; contado 250 → sobrante de 50 (revisión).
    cut = conn.execute("SELECT expected_cash, counted_cash, difference FROM cash_cuts WHERE id=?",
                       (z.entity_id,)).fetchone()
    assert (Decimal(cut[0]), Decimal(cut[1]), Decimal(cut[2])) == (
        Decimal("200"), Decimal("250"), Decimal("50"))
    diff = conn.execute("SELECT id, severity FROM cash_differences WHERE z_cut_id=?",
                        (z.entity_id,)).fetchone()
    assert diff[1] == "REVIEW"

    # 7. Diferencia con dos personas: el cajero explica, la dueña revisa y resuelve.
    cajero.explain_cash_difference(difference_id=diff[0], explanation="Cambio mal entregado")
    with pytest.raises(CashSegregationOfDutiesError):
        cajero.review_cash_difference(difference_id=diff[0])
    duena.review_cash_difference(difference_id=diff[0])
    duena.resolve_cash_difference(difference_id=diff[0], resolution="Se repone y se documenta")
    assert tuple(conn.execute("SELECT status, resolved_by FROM cash_differences WHERE id=?",
                              (diff[0],)).fetchone()) == ("RESOLVED", owner_id)


def test_cashier_cannot_resolve_or_configure(conn):
    owner_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    cashier_id = new_uuid()
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
                 " VALUES (?, 'Ana', 'ana', 'x', 'cajero', ?, 1)", (cashier_id, branch_id))
    conn.commit()
    caps = build_cash_register_presenter(
        _Root(conn, _session(conn, cashier_id, branch_id, "cajero"))).capabilities()
    assert caps.shift_open and caps.module_view
    assert not caps.difference_resolve
    assert not caps.settings_view


def test_reopening_caja_mid_count_recovers_the_open_count(conn):
    owner_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    now = "2026-08-03T00:00:00+00:00"
    register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch_id, "CAJA-01", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch_id, register, "CAJON-01", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch_id, register, "TER-01", "ACTIVE", now, now))
    conn.commit()
    session = _session(conn, owner_id, branch_id, "system_owner")
    first = build_cash_register_presenter(_Root(conn, session))
    first.open_cash_shift(opening_amount=Decimal("0"))
    first.begin_cash_shift_closing()
    count = first.start_blind_count()
    # Caja se cierra y se vuelve a abrir: nueva composición, sin memoria previa.
    reopened = build_cash_register_presenter(_Root(conn, session))
    assert reopened.active_count_context()[0] == count.entity_id
