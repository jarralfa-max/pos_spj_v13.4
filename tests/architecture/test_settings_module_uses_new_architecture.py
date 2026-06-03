from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")

REQUIRED_SERVICES = [
    "SettingsApplicationService",
    "SystemSettingsService",
    "CompanyProfileService",
    "EmailSettingsService",
    "PaymentProviderSettingsService",
    "ClosingPeriodService",
    "UserManagementService",
    "RoleManagementService",
    "PermissionQueryService",
    "ModuleAccessService",
]

FORBIDDEN_ROUTES = [
    "self.config_repository.",
    "get_ticket_design_elements",
    "get_hardware_configs",
    "get_loyalty_weights",
    "list_whatsapp_numbers",
    "save_legacy_user",
    "self.conexion.execute",
    "self.conexion.commit",
    "self.conexion.rollback",
    "cursor.execute",
]


def test_settings_module_uses_only_canonical_services_for_persistence() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    missing = [service for service in REQUIRED_SERVICES if service not in content]
    forbidden = [route for route in FORBIDDEN_ROUTES if route in content]
    assert not missing, "Missing canonical services: " + ", ".join(missing)
    assert not forbidden, "Forbidden old persistence routes: " + ", ".join(forbidden)
