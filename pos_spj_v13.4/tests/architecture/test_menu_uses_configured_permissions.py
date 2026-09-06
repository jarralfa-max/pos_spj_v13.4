from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT

MENU = (APP_ROOT / "interfaz/menu_lateral.py")
MAIN_WINDOW = (APP_ROOT / "interfaz/main_window.py")
CONFIGURATION_MODULE = (APP_ROOT / "modulos/configuracion.py")


def test_menu_lateral_uses_configured_permissions_not_hardcoded_roles() -> None:
    content = MENU.read_text(encoding="utf-8")

    forbidden = ["SOLO_ADMIN_GERENTE", "SOLO_ADMIN", "GERENTE_O_SUPERIOR"]
    assert not [token for token in forbidden if token in content]
    assert '"*"' in content
    assert 'f"{codigo}.ver"' in content or "codigo + '.ver'" in content


def test_main_window_and_settings_refresh_configured_permissions() -> None:
    main_content = MAIN_WINDOW.read_text(encoding="utf-8")
    settings_content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "PermissionQueryService" in main_content
    assert "get_permisos" not in main_content
    assert "def refresh_module_access" in main_content
    assert "refresh_module_access()" in settings_content
