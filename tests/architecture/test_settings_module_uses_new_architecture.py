from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")

REQUIRED_SERVICE_ATTRIBUTES = [
    "settings_application_service",
    "system_settings_service",
    "company_profile_service",
    "email_settings_service",
    "payment_provider_settings_service",
    "closing_period_service",
    "happy_hour_settings_service",
    "user_management_service",
    "role_management_service",
    "permission_query_service",
    "module_access_service",
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
    missing = [service for service in REQUIRED_SERVICE_ATTRIBUTES if service not in content]
    forbidden = [route for route in FORBIDDEN_ROUTES if route in content]

    assert "SettingsModuleServices.from_connection" in content
    assert "settings_application_service.assert_ready()" in content
    assert not missing, "Missing canonical service attributes: " + ", ".join(missing)
    assert not forbidden, "Forbidden old persistence routes: " + ", ".join(forbidden)
