import inspect
from pathlib import Path

from backend.application.inventory.permissions import (
    ALL_INVENTORY_PERMISSIONS,
    InventoryPermissions,
)
from backend.application.inventory.session_authorization import (
    InventorySessionPermissionChecker,
)
from backend.security.permissions.codes import permission_code
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS

ROOT = Path(__file__).resolve().parents[2]
#: La UI enterprise legacy (`modulos/inventario_enterprise.py`) ya no existe.
#: El guardrail no se borra por eso: apunta ahora a la UI canónica viva, que es
#: donde hoy podría reaparecer el vocabulario grueso que INV-27 retiró.
INVENTORY_UI_PACKAGE = ROOT / "frontend/desktop/modules/inventory"

_LEGACY_CODES = (
    "inventario.ver", "inventario.editar", "inventario.ajustar",
    "inventario.transferir",
)


def test_inventory_uses_canonical_permissions() -> None:
    # INV-27 corte: la UI enterprise es de solo lectura (presenter); no lleva
    # cadenas de permiso legacy. Los permisos granulares viven en la navegación
    # canónica (InventoryPermissions), verificada por los tests de INV-25.
    assert INVENTORY_UI_PACKAGE.is_dir(), INVENTORY_UI_PACKAGE
    for path in sorted(INVENTORY_UI_PACKAGE.rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        for legacy in ('"inventario.entrada"', '"inventario.ajustar"',
                       "INVENTARIO.entrada", "INVENTARIO.ajustar"):
            assert legacy not in content, f"{path}: {legacy}"


# ── INV-1 §60-61: sin vocabulario legacy en runtime ─────────────────────────
def test_no_inventory_prefixed_runtime_codes() -> None:
    for code in ALL_INVENTORY_PERMISSIONS:
        assert not code.startswith("INVENTORY_"), code


def test_no_legacy_bare_module_permission_codes_reachable() -> None:
    for code in ALL_INVENTORY_PERMISSIONS:
        assert code not in _LEGACY_CODES


def test_session_checker_has_no_legacy_translation() -> None:
    src = inspect.getsource(InventorySessionPermissionChecker)
    assert "legacy_codes_for" not in src
    assert "legacy" not in src.lower()


def test_no_legacy_codes_for_function_exists() -> None:
    import backend.application.inventory.session_authorization as mod
    assert not hasattr(mod, "legacy_codes_for")


# ── INV-1: catálogo canónico y enum en lockstep ─────────────────────────────
def test_catalog_and_enum_are_in_lockstep() -> None:
    catalog_codes = {
        permission_code("INVENTARIO", action)
        for action in CANONICAL_MODULE_PERMISSIONS["INVENTARIO"]
    }
    enum_codes = set(ALL_INVENTORY_PERMISSIONS)
    assert enum_codes == catalog_codes, (
        f"En el catálogo pero no en el enum: {catalog_codes - enum_codes}\n"
        f"En el enum pero no en el catálogo: {enum_codes - catalog_codes}")


def test_all_inventory_permission_values_use_module_action_format() -> None:
    for name, value in vars(InventoryPermissions).items():
        if name.startswith("_") or not isinstance(value, str):
            continue
        assert value.startswith("INVENTARIO."), f"{name}={value}"
        assert value == value.strip()
        action = value.split(".", 1)[1]
        assert action == action.lower(), f"{name}={value} (acción debe ser minúscula)"
