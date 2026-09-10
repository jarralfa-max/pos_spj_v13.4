import re
from pathlib import Path

from backend.security.permissions.codes import module_view_permission, permission_code, normalize_permission
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from tests.architecture.architecture_guardrails import APP_ROOT

MENU = (APP_ROOT / "interfaz/menu_lateral.py")


def test_permission_catalog_has_all_menu_modules() -> None:
    content = MENU.read_text(encoding="utf-8")
    modules = set(re.findall(r'_crear_boton\("[^"]+",\s*"([^"]+)"\)', content))
    modules.discard("LOGOUT")

    missing = sorted(module for module in modules if module not in CANONICAL_MODULE_PERMISSIONS)
    assert not missing, "Missing canonical module permissions: " + ", ".join(missing)


def test_permission_helpers_normalize_canonical_codes() -> None:
    assert permission_code("pos", "VER") == "POS.ver"
    assert module_view_permission("pos") == "POS.ver"
    assert normalize_permission("pos.ver") == "POS.VER"
