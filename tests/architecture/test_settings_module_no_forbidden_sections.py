from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


FORBIDDEN_TOKENS = [
    "crear_tab_fidelizacion",
    "crear_tab_hardware",
    "crear_tab_ticket_designer",
    "_setup_tab_whatsapp",
    "_toggle_dark_mode",
    "LoyaltyProgramSettingsService",
    "get_legacy_users",
    "DialogoUsuario",
    "tabla_usuarios",
    "legacy",
    "compat",
    "fallback",
]


def test_settings_module_has_no_forbidden_sections_or_legacy_routes() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8").lower()
    violations = [token for token in FORBIDDEN_TOKENS if token.lower() in content]
    assert not violations, "Forbidden Configuración remnants: " + ", ".join(violations)
