"""FASE 6 — canonical use-case flow tests for CONFIGURACION.

Each mutation has exactly one route: Command -> UseCase -> application service
(UnitOfWork + repository, event post-commit).
"""

from __future__ import annotations

import sqlite3
from uuid import UUID

from backend.application.commands.settings_commands import (
    ExecuteMonthlyClosingCommand,
    SaveHappyHourRuleCommand,
    SaveHardwareConfigCommand,
    SaveModuleToggleCommand,
    SaveRolePermissionsCommand,
    SaveUserCommand,
)
from backend.application.use_cases.execute_monthly_closing_use_case import ExecuteMonthlyClosingUseCase
from backend.application.use_cases.save_happy_hour_rule_use_case import SaveHappyHourRuleUseCase
from backend.application.use_cases.save_hardware_config_use_case import SaveHardwareConfigUseCase
from backend.application.use_cases.save_module_toggle_use_case import SaveModuleToggleUseCase
from backend.application.use_cases.save_role_permissions_use_case import SaveRolePermissionsUseCase
from backend.application.use_cases.save_user_use_case import SaveUserUseCase
from backend.application.use_cases.save_system_setting_use_case import SaveSystemSettingUseCase
from backend.application.use_cases.save_company_profile_use_case import SaveCompanyProfileUseCase
from backend.application.use_cases.save_smtp_settings_use_case import SaveSMTPSettingsUseCase
from backend.application.use_cases.save_payment_provider_settings_use_case import SavePaymentProviderSettingsUseCase
from backend.application.use_cases.set_user_active_use_case import SetUserActiveUseCase
from backend.application.use_cases.set_happy_hour_rule_active_use_case import SetHappyHourRuleActiveUseCase
from backend.application.commands.settings_commands import (
    SaveSystemSettingCommand,
    SaveCompanyProfileCommand,
    SaveSMTPSettingsCommand,
    SavePaymentProviderSettingsCommand,
    SetUserActiveCommand,
    SetHappyHourRuleActiveCommand,
)
from backend.application.services.hardware_settings_service import HardwareSettingsService
from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    ClosingPeriodService,
    HappyHourSettingsService,
    ModuleAccessService,
    ModuleSettingsService,
    PermissionEventPublisher,
    UserManagementService,
)
from repositories.config_repository import ConfigRepository


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, usuario TEXT, nombre TEXT,
            email TEXT, rol TEXT, sucursal_id INTEGER, sucursal_uuid TEXT, activo INTEGER DEFAULT 1,
            empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE rol_permisos(rol_id INTEGER, rol_uuid TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE happy_hour_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT,
            hora_inicio TEXT, hora_fin TEXT, dias_semana TEXT, tipo_descuento TEXT, valor REAL,
            aplica_a TEXT, aplica_valor TEXT, mensaje_wa TEXT, activo INTEGER, sucursal_uuid TEXT);
        CREATE TABLE cierre_mensual(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, periodo TEXT,
            cerrado_por TEXT, fecha_cierre TEXT, total_ventas REAL, total_compras REAL, total_merma REAL,
            sucursal_uuid TEXT);
        CREATE TABLE module_toggles(clave TEXT PRIMARY KEY, activo INTEGER DEFAULT 1, descripcion TEXT DEFAULT '');
        CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT);
        """
    )
    branch_uuid = new_uuid()
    conn.execute("INSERT INTO sucursales(uuid, nombre, activa) VALUES(?, 'Centro', 1)", (branch_uuid,))
    role_uuid = new_uuid()
    conn.execute("INSERT INTO roles(uuid, nombre, descripcion) VALUES(?, 'gerente', 'Gerente')", (role_uuid,))
    conn.commit()
    return conn, branch_uuid, role_uuid


def test_create_user_flow():
    conn, branch_uuid, _ = _conn()
    publisher = PermissionEventPublisher()
    uc = SaveUserUseCase(UserManagementService(ConfigRepository(conn), publisher))
    cmd = SaveUserCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        username="ana", full_name="Ana", email="ana@x.mx", role="gerente",
        active=True,
    )
    result = uc.execute(cmd)
    assert result.success and UUID(result.entity_id).version == 7
    row = conn.execute("SELECT usuario, uuid FROM usuarios WHERE usuario='ana'").fetchone()
    assert row["uuid"] == result.entity_id
    assert publisher.published_events[-1]["event_name"] == "USER_PERMISSIONS_UPDATED"


def test_save_role_permissions_flow():
    conn, _, role_uuid = _conn()
    publisher = PermissionEventPublisher()
    uc = SaveRolePermissionsUseCase(ModuleAccessService(ConfigRepository(conn), publisher))
    cmd = SaveRolePermissionsCommand(
        operation_id=new_uuid(), branch_id=new_uuid(), user_name="admin",
        role_id=role_uuid,
        permissions=({"module": "CONFIG_SEGURIDAD", "action": "editar", "allowed": True},),
    )
    result = uc.execute(cmd)
    assert result.success
    saved = conn.execute("SELECT permitido FROM rol_permisos WHERE rol_uuid=? AND modulo='CONFIG_SEGURIDAD'", (role_uuid,)).fetchone()
    assert saved["permitido"] == 1
    names = [e["event_name"] for e in publisher.published_events]
    assert "ROLE_PERMISSIONS_UPDATED" in names and "MODULE_ACCESS_UPDATED" in names


def test_execute_monthly_closing_flow():
    conn, branch_uuid, _ = _conn()
    uc = ExecuteMonthlyClosingUseCase(ClosingPeriodService(ConfigRepository(conn)))
    cmd = ExecuteMonthlyClosingCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        period="2026-05", payload={"sales": 1000, "purchases": 400, "waste": 50},
    )
    result = uc.execute(cmd)
    assert result.success and result.entity_id == "2026-05"
    row = conn.execute("SELECT total_ventas FROM cierre_mensual WHERE periodo='2026-05'").fetchone()
    assert row["total_ventas"] == 1000
    # idempotent guard: second close rejected
    assert uc.execute(cmd).success is False


def test_save_happy_hour_rule_flow():
    conn, branch_uuid, _ = _conn()
    uc = SaveHappyHourRuleUseCase(HappyHourSettingsService(ConfigRepository(conn)))
    cmd = SaveHappyHourRuleCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        name="Tarde", start_time="16:00", end_time="18:00",
        discount_percent=10.0, days_of_week=(1, 2, 3), active=True,
    )
    result = uc.execute(cmd)
    assert result.success and UUID(result.entity_id).version == 7
    row = conn.execute("SELECT nombre, valor FROM happy_hour_rules WHERE uuid=?", (result.entity_id,)).fetchone()
    assert row["nombre"] == "Tarde" and row["valor"] == 10.0


def test_save_hardware_config_flow():
    conn, _, _ = _conn()
    service = HardwareSettingsService(conn)
    uc = SaveHardwareConfigUseCase(service)
    cmd = SaveHardwareConfigCommand(
        operation_id=new_uuid(), branch_id=new_uuid(), user_name="admin",
        device_type="ticket", config={"ubicacion": "192.168.1.50:9100"},
    )
    result = uc.execute(cmd)
    assert result.success and result.entity_id == "ticket"
    assert service.load_all()["ticket"]["ubicacion"] == "192.168.1.50:9100"


def test_save_module_toggle_flow():
    conn, _, _ = _conn()
    service = ModuleSettingsService(ConfigRepository(conn))
    uc = SaveModuleToggleUseCase(service)
    cmd = SaveModuleToggleCommand(
        operation_id=new_uuid(), branch_id=new_uuid(), user_name="admin",
        key="loyalty", enabled=True,
    )
    result = uc.execute(cmd)
    assert result.success and result.entity_id == "loyalty"
    assert service.is_enabled("loyalty") is True


def test_save_system_setting_flow():
    conn, branch_uuid, _ = _conn()
    from core.services.configuration_settings_service import SystemSettingsService
    svc = SystemSettingsService(ConfigRepository(conn))
    uc = SaveSystemSettingUseCase(svc)
    cmd = SaveSystemSettingCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        key="tasa_iva", value="16.0",
    )
    assert uc.execute(cmd).success
    assert svc.get_setting("tasa_iva") == "16.0"


def test_save_company_profile_flow():
    conn, branch_uuid, _ = _conn()
    from core.services.configuration_settings_service import SystemSettingsService
    svc = SystemSettingsService(ConfigRepository(conn))
    uc = SaveCompanyProfileUseCase(svc)
    cmd = SaveCompanyProfileCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        name="SPJ", rfc="XAXX010101000", phone="+5215500000000",
    )
    assert uc.execute(cmd).success
    assert svc.get_setting("nombre_empresa") == "SPJ"
    assert svc.get_setting("rfc") == "XAXX010101000"


def test_save_smtp_and_payment_provider_flow():
    conn, branch_uuid, _ = _conn()
    from core.services.configuration_settings_service import (
        EmailSettingsService, PaymentProviderSettingsService, SystemSettingsService,
    )
    sys_svc = SystemSettingsService(ConfigRepository(conn))
    assert SaveSMTPSettingsUseCase(EmailSettingsService(sys_svc)).execute(
        SaveSMTPSettingsCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                host="smtp.x.mx", port=587, username="u", password="p", from_email="g@x.mx")
    ).success
    assert sys_svc.get_setting("smtp_host") == "smtp.x.mx"

    assert SavePaymentProviderSettingsUseCase(PaymentProviderSettingsService(sys_svc)).execute(
        SavePaymentProviderSettingsCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                           access_token="TOK", webhook_url="http://x")
    ).success
    assert sys_svc.get_setting("mp_access_token") == "TOK"


def test_set_user_active_flow():
    conn, branch_uuid, _ = _conn()
    publisher = PermissionEventPublisher()
    user_svc = UserManagementService(ConfigRepository(conn), publisher)
    uid = SaveUserUseCase(user_svc).execute(
        SaveUserCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
                        username="ana", role="gerente")
    ).entity_id
    res = SetUserActiveUseCase(user_svc).execute(
        SetUserActiveCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
                             user_id=uid, active=False)
    )
    assert res.success
    assert conn.execute("SELECT activo FROM usuarios WHERE uuid=?", (uid,)).fetchone()["activo"] == 0


def test_set_happy_hour_rule_active_flow():
    conn, branch_uuid, _ = _conn()
    hh = HappyHourSettingsService(ConfigRepository(conn))
    rid = SaveHappyHourRuleUseCase(hh).execute(
        SaveHappyHourRuleCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                 name="Tarde", discount_percent=10.0, active=True)
    ).entity_id
    assert SetHappyHourRuleActiveUseCase(hh).execute(
        SetHappyHourRuleActiveCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                      rule_id=rid, active=False)
    ).success
    assert conn.execute("SELECT activo FROM happy_hour_rules WHERE uuid=?", (rid,)).fetchone()["activo"] == 0


def test_command_validation_rejects_missing_fields():
    import pytest
    with pytest.raises(ValueError):
        SaveUserUseCase(None).execute(
            SaveUserCommand(operation_id=new_uuid(), branch_id=new_uuid(), user_name="admin", username="", role="x")
        )
