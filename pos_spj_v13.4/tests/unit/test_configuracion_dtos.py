"""FASE 4 — DTO contract and DTO-returning query service tests for CONFIGURACION."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from uuid import UUID

from backend.application.dto.configuracion_dtos import (
    BranchDeliveryRowDTO,
    HappyHourRuleDTO,
    MonthlyClosingSummaryDTO,
    RoleSettingsDTO,
    UserSettingsDTO,
)
from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    ClosingPeriodService,
    CompanyProfileService,
    HappyHourSettingsService,
    RoleManagementService,
    UserManagementService,
)
from repositories.config_repository import ConfigRepository

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_UI = PACKAGE_ROOT / "modulos" / "configuracion.py"


# --- DTO identity contracts ------------------------------------------------
def test_happy_hour_rule_dto_has_uuid_identity() -> None:
    rid = new_uuid()
    dto = HappyHourRuleDTO(id=rid, name="Tarde feliz")
    assert dto.id == rid
    assert UUID(dto.id).version == 7
    assert dto.id == dto.id.lower()


def test_user_settings_dto_has_uuid_identity() -> None:
    uid = new_uuid()
    dto = UserSettingsDTO(id=uid, username="ana")
    assert dto.id == uid
    assert UUID(dto.id).version == 7
    assert dto.id == dto.id.lower()


def test_role_settings_dto_has_uuid_identity() -> None:
    rid = new_uuid()
    dto = RoleSettingsDTO(id=rid, name="gerente")
    assert dto.id == rid
    assert UUID(dto.id).version == 7


# --- DTO-returning query services -----------------------------------------
def _canonical_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT,
            direccion TEXT, telefono TEXT, hora_apertura TEXT, hora_cierre TEXT,
            dias_operacion TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, usuario TEXT, nombre TEXT,
            email TEXT, rol TEXT, sucursal_id INTEGER, sucursal_uuid TEXT, activo INTEGER DEFAULT 1, empleado_id INTEGER);
        CREATE TABLE happy_hour_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT,
            hora_inicio TEXT, hora_fin TEXT, dias_semana TEXT, tipo_descuento TEXT, valor REAL,
            aplica_a TEXT, aplica_valor TEXT, mensaje_wa TEXT, activo INTEGER, sucursal_uuid TEXT);
        CREATE TABLE cierre_mensual(periodo TEXT, cerrado_por TEXT, fecha_cierre TEXT,
            total_ventas REAL, total_compras REAL, total_merma REAL);
        """
    )
    suc_uuid = new_uuid()
    conn.execute(
        "INSERT INTO sucursales(uuid, nombre, direccion, hora_apertura, hora_cierre, dias_operacion, activa) "
        "VALUES(?, 'Centro', 'MX', '08:00', '20:00', '1,2,3', 1)",
        (suc_uuid,),
    )
    conn.execute("INSERT INTO roles(uuid, nombre, descripcion) VALUES(?, 'gerente', 'Gerente')", (new_uuid(),))
    conn.execute(
        "INSERT INTO usuarios(uuid, usuario, nombre, email, rol, sucursal_uuid, activo, empleado_id) "
        "VALUES(?, 'ana', 'Ana', 'ana@x.mx', 'gerente', ?, 1, NULL)",
        (new_uuid(), suc_uuid),
    )
    conn.execute(
        "INSERT INTO happy_hour_rules(uuid, nombre, hora_inicio, hora_fin, dias_semana, tipo_descuento, "
        "valor, aplica_a, aplica_valor, mensaje_wa, activo, sucursal_uuid) "
        "VALUES(?, 'Tarde', '16:00', '18:00', '1,2', 'porcentaje', 10.0, 'todos', '', 'hola', 1, ?)",
        (new_uuid(), suc_uuid),
    )
    conn.execute(
        "INSERT INTO cierre_mensual(periodo, cerrado_por, fecha_cierre, total_ventas, total_compras, total_merma) "
        "VALUES('2026-05', 'admin', '2026-06-01T10:00:00', 1000.0, 400.0, 50.0)"
    )
    conn.commit()
    return conn


def test_configuration_query_services_return_dtos() -> None:
    repo = ConfigRepository(_canonical_conn())

    rules = HappyHourSettingsService(repo).list_rules()
    assert rules and all(isinstance(r, HappyHourRuleDTO) for r in rules)
    assert rules[0].name == "Tarde" and rules[0].discount_type == "porcentaje"

    users = UserManagementService(repo).list_users()
    assert users and all(isinstance(u, UserSettingsDTO) for u in users)
    assert users[0].username == "ana" and users[0].role == "gerente"

    roles = RoleManagementService(repo).list_roles()
    assert roles and all(isinstance(r, RoleSettingsDTO) for r in roles)
    assert roles[0].name == "gerente"

    branches = CompanyProfileService(repo).list_branch_delivery_rows()
    assert branches and all(isinstance(b, BranchDeliveryRowDTO) for b in branches)
    assert branches[0].name == "Centro"

    closings = ClosingPeriodService(repo).history()
    assert closings and all(isinstance(c, MonthlyClosingSummaryDTO) for c in closings)
    assert closings[0].period == "2026-05" and closings[0].total_sales == 1000.0


def test_user_form_dto_round_trips_uuid_identity() -> None:
    conn = _canonical_conn()
    repo = ConfigRepository(conn)
    user_uuid = conn.execute("SELECT uuid FROM usuarios WHERE usuario='ana'").fetchone()[0]

    dto = UserManagementService(repo).get_user_form_data(user_uuid)
    assert isinstance(dto, UserSettingsDTO)
    assert dto.id == user_uuid
    assert dto.email == "ana@x.mx"


# --- UI no longer consumes raw rows ---------------------------------------
def test_configuracion_ui_no_tuple_indexing_for_service_rows() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")
    # No ambiguous dict access on rule rows.
    assert 'rule["id"]' not in content
    assert "rule.get(" not in content
    # No positional indexing of service result rows (r[0], row[1], ...).
    assert not re.search(r"\br\[\d", content), "positional r[N] indexing found"
    assert not re.search(r"\brow\[\d", content), "positional row[N] indexing found"
    # Positive: entity rows are consumed by attribute.
    assert "user.username" in content
    assert "role.name" in content
    assert "rule.name" in content
