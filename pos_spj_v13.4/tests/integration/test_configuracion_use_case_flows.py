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
    SaveRoleCommand,
    SaveRolePermissionsCommand,
    SaveUserCommand,
    SetInstallationBranchCommand,
)
from backend.application.use_cases.execute_monthly_closing_use_case import ExecuteMonthlyClosingUseCase
from backend.application.use_cases.save_happy_hour_rule_use_case import SaveHappyHourRuleUseCase
from backend.application.use_cases.save_module_toggle_use_case import SaveModuleToggleUseCase
from backend.application.use_cases.save_role_permissions_use_case import SaveRolePermissionsUseCase
from backend.application.use_cases.save_role_use_case import SaveRoleUseCase
from backend.application.use_cases.save_user_use_case import SaveUserUseCase
from backend.application.use_cases.save_system_setting_use_case import SaveSystemSettingUseCase
from backend.application.use_cases.save_company_profile_use_case import SaveCompanyProfileUseCase
from backend.application.use_cases.save_smtp_settings_use_case import SaveSMTPSettingsUseCase
from backend.application.use_cases.save_payment_provider_settings_use_case import SavePaymentProviderSettingsUseCase
from backend.application.use_cases.set_user_active_use_case import SetUserActiveUseCase
from backend.application.use_cases.set_happy_hour_rule_active_use_case import SetHappyHourRuleActiveUseCase
from backend.application.use_cases.set_installation_branch_use_case import SetInstallationBranchUseCase
from backend.application.commands.settings_commands import (
    SaveSystemSettingCommand,
    SaveCompanyProfileCommand,
    SaveSMTPSettingsCommand,
    SavePaymentProviderSettingsCommand,
    SetUserActiveCommand,
    SetHappyHourRuleActiveCommand,
)
from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    ClosingPeriodService,
    CompanyProfileService,
    HappyHourSettingsService,
    ModuleAccessService,
    ModuleSettingsService,
    PermissionEventPublisher,
    RoleManagementService,
    UserManagementService,
)
from repositories.config_repository import ConfigRepository


def _conn():
    # Born-clean schema: id columns ARE the UUIDv7 identity directly (no
    # separate int/uuid dual-column pair) — mirrors migrations/
    # m000_base_schema.py + migrations/standalone/047_v13_schema.py
    # (usuarios.empleado_id/email) + 046_comisiones_happy_hour.py
    # (happy_hour_rules), the real, current shape `ConfigRepository`
    # already reads/writes against. The previous hand-rolled
    # `INTEGER PRIMARY KEY AUTOINCREMENT` + `uuid TEXT` layout predates
    # that cutover and made every mutation here raise
    # `sqlite3.IntegrityError: datatype mismatch` (a UUID string can't be
    # coerced into a rowid-alias INTEGER column).
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE roles(id TEXT PRIMARY KEY, nombre TEXT UNIQUE, descripcion TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE usuarios(id TEXT PRIMARY KEY, usuario TEXT, nombre TEXT,
            email TEXT, rol TEXT, sucursal_id TEXT, activo INTEGER DEFAULT 1,
            empleado_id TEXT, password_hash TEXT, intentos_fallidos INTEGER DEFAULT 0,
            bloqueado_hasta DATETIME);
        CREATE TABLE rol_permisos(id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE happy_hour_rules(id TEXT PRIMARY KEY, nombre TEXT,
            hora_inicio TEXT, hora_fin TEXT, dias_semana TEXT, tipo_descuento TEXT, valor REAL,
            aplica_a TEXT, aplica_valor TEXT, mensaje_wa TEXT, activo INTEGER, sucursal_id TEXT);
        CREATE TABLE cierre_mensual(id TEXT PRIMARY KEY, periodo TEXT,
            cerrado_por TEXT, fecha_cierre TEXT, total_ventas REAL, total_compras REAL, total_merma REAL,
            sucursal_id TEXT);
        CREATE TABLE module_toggles(clave TEXT PRIMARY KEY, activo INTEGER DEFAULT 1, descripcion TEXT DEFAULT '');
        CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT);
        CREATE TABLE hardware_config(tipo TEXT PRIMARY KEY, nombre TEXT, driver TEXT, puerto TEXT,
            configuraciones TEXT, activo INTEGER DEFAULT 1, sucursal_id TEXT,
            fecha_actualizacion DATETIME DEFAULT (datetime('now')));
        """
    )
    branch_uuid = new_uuid()
    conn.execute("INSERT INTO sucursales(id, nombre, activa) VALUES(?, 'Centro', 1)", (branch_uuid,))
    role_uuid = new_uuid()
    conn.execute("INSERT INTO roles(id, nombre, descripcion) VALUES(?, 'gerente', 'Gerente')", (role_uuid,))
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
    row = conn.execute("SELECT usuario, id FROM usuarios WHERE usuario='ana'").fetchone()
    assert row["id"] == result.entity_id
    assert publisher.published_events[-1]["event_name"] == "USER_PERMISSIONS_UPDATED"


def test_save_role_flow():
    conn, branch_uuid, _ = _conn()
    publisher = PermissionEventPublisher()
    uc = SaveRoleUseCase(RoleManagementService(ConfigRepository(conn), publisher))
    cmd = SaveRoleCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        name="supervisor", description="Supervisor de turno",
    )
    result = uc.execute(cmd)
    assert result.success and UUID(result.entity_id).version == 7
    row = conn.execute("SELECT nombre, descripcion FROM roles WHERE id=?", (result.entity_id,)).fetchone()
    assert row["nombre"] == "supervisor" and row["descripcion"] == "Supervisor de turno"

    # updating the same role keeps its id and changes only the description
    update_cmd = SaveRoleCommand(
        operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin",
        role_id=result.entity_id, name="supervisor", description="Actualizado",
    )
    updated = uc.execute(update_cmd)
    assert updated.entity_id == result.entity_id
    row = conn.execute("SELECT descripcion FROM roles WHERE id=?", (result.entity_id,)).fetchone()
    assert row["descripcion"] == "Actualizado"


def test_set_installation_branch_flow():
    conn, branch_uuid, _ = _conn()
    inactive_branch_uuid = new_uuid()
    conn.execute(
        "INSERT INTO sucursales(id, nombre, activa) VALUES(?, 'Sucursal inactiva', 0)",
        (inactive_branch_uuid,),
    )
    conn.commit()
    uc = SetInstallationBranchUseCase(CompanyProfileService(ConfigRepository(conn)))

    cmd = SetInstallationBranchCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="admin")
    result = uc.execute(cmd)
    assert result.success and result.entity_id == branch_uuid and result.data["branch_name"] == "Centro"
    row = conn.execute(
        "SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'"
    ).fetchone()
    assert row["valor"] == branch_uuid
    assert ConfigRepository(conn).get_installation_branch() == (branch_uuid, "Centro")

    # an inactive branch is rejected, never persisted
    bad_cmd = SetInstallationBranchCommand(
        operation_id=new_uuid(), branch_id=inactive_branch_uuid, user_name="admin")
    try:
        uc.execute(bad_cmd)
        assert False, "expected ValueError for an inactive branch"
    except ValueError:
        pass
    assert ConfigRepository(conn).get_installation_branch() == (branch_uuid, "Centro")


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
    saved = conn.execute("SELECT permitido FROM rol_permisos WHERE rol_id=? AND modulo='CONFIG_SEGURIDAD'", (role_uuid,)).fetchone()
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
    row = conn.execute("SELECT nombre, valor FROM happy_hour_rules WHERE id=?", (result.entity_id,)).fetchone()
    assert row["nombre"] == "Tarde" and row["valor"] == 10.0


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


def test_save_smtp_and_payment_provider_flow(tmp_path):
    conn, branch_uuid, _ = _conn()
    from core.services.configuration_settings_service import (
        EmailSettingsService, PaymentProviderSettingsService, SystemSettingsService,
    )
    from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore
    sys_svc = SystemSettingsService(ConfigRepository(conn))
    secret_store = EncryptedLocalSecretStore(store_dir=tmp_path / "secrets")
    email_svc = EmailSettingsService(sys_svc, secret_store)
    assert SaveSMTPSettingsUseCase(email_svc).execute(
        SaveSMTPSettingsCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                host="smtp.x.mx", port=587, username="u", password="p", from_email="g@x.mx")
    ).success
    assert sys_svc.get_setting("smtp_host") == "smtp.x.mx"
    # smtp_password must never land in the plaintext settings table.
    assert sys_svc.get_setting("smtp_password") == ""
    assert secret_store.get_secret(EmailSettingsService.SECRET_NAME) == "p"
    assert email_svc.get_settings()["smtp_password"] == "p"

    payment_svc = PaymentProviderSettingsService(sys_svc, secret_store)
    assert SavePaymentProviderSettingsUseCase(payment_svc).execute(
        SavePaymentProviderSettingsCommand(operation_id=new_uuid(), branch_id=branch_uuid, user_name="a",
                                           access_token="TOK", webhook_url="http://x")
    ).success
    # mp_access_token must never land in the plaintext settings table either.
    assert sys_svc.get_setting("mp_access_token") == ""
    assert secret_store.get_secret(PaymentProviderSettingsService.SECRET_NAME) == "TOK"
    assert payment_svc.get_mercado_pago_settings()["mp_access_token"] == "TOK"


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
    assert conn.execute("SELECT activo FROM usuarios WHERE id=?", (uid,)).fetchone()["activo"] == 0


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
    assert conn.execute("SELECT activo FROM happy_hour_rules WHERE id=?", (rid,)).fetchone()["activo"] == 0


def test_command_validation_rejects_missing_fields():
    import pytest
    with pytest.raises(ValueError):
        SaveUserUseCase(None).execute(
            SaveUserCommand(operation_id=new_uuid(), branch_id=new_uuid(), user_name="admin", username="", role="x")
        )
