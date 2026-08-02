"""P0-A guardrail (§5.1/§19.3) — la autorización de Inventario falla cerrado.

- `InventoryAuthorizationPolicy` sin `PermissionChecker` NO permite: lanza
  `InventoryConfigurationError` (nunca hace un ``return`` silencioso que autorice).
- Ningún caso de uso de aplicación construye la política con el default vacío
  `InventoryAuthorizationPolicy()` (fail-open). El default explícito es
  `permissive_for_tests()`, y producción inyecta un checker real.
- Los helpers permisivos/denegadores de pruebas existen para no depender del
  fail-open.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    DenyAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.domain.inventory.exceptions import InventoryConfigurationError

_ROOT = Path(__file__).resolve().parents[2]
_USE_CASES_DIR = _ROOT / "backend/application/inventory"


def test_policy_without_checker_fails_closed():
    with pytest.raises(InventoryConfigurationError):
        InventoryAuthorizationPolicy().require(
            "u1", InventoryPermissions.MOVEMENT_CREATE)


def test_probe_without_checker_is_false_not_true():
    assert InventoryAuthorizationPolicy().has_permission(
        "u1", InventoryPermissions.MOVEMENT_CREATE) is False


def test_test_only_checkers_exist_and_behave():
    assert AllowAllInventoryPermissionCheckerForTests().has_permission("u", "x")
    assert not DenyAllInventoryPermissionCheckerForTests().has_permission("u", "x")


def test_no_use_case_uses_fail_open_empty_default():
    """Ningún archivo de aplicación conserva `or InventoryAuthorizationPolicy()`
    (fail-open). El default debe ser `permissive_for_tests()`."""
    offenders: list[str] = []
    pattern = re.compile(r"or\s+InventoryAuthorizationPolicy\(\)")
    for path in _USE_CASES_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(_ROOT)))
    assert offenders == [], (
        "Default fail-open de autorización (usa permissive_for_tests()):\n"
        + "\n".join(sorted(offenders)))


def test_inventory_ui_has_no_fabricated_identity_fallback():
    """§5.4: la UI de inventario no fabrica identidad/ámbito con literales
    ("desktop"/"MAIN"/"1"/"system"), y `default_warehouse` no cae en la sucursal
    (warehouse_id = branch_id). Sin sesión, los valores quedan vacíos."""
    import re
    ui_files = [
        _ROOT / "frontend/desktop/modules/inventory/presenter.py",
        _ROOT / "modulos/inventario_enterprise.py",
    ]
    literal_fallback = re.compile(r"\bor\s+[\"'](desktop|MAIN|Sistema|system|1)[\"']")
    offenders: list[str] = []
    for path in ui_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]  # ignora comentarios
            if literal_fallback.search(code):
                offenders.append(f"{path.relative_to(_ROOT)}: {code.strip()}")
    # default_warehouse no debe reusar la sucursal como almacén.
    presenter_src = ui_files[0].read_text(encoding="utf-8")
    dw_body = presenter_src.split("def default_warehouse(", 1)[1].split("def ", 1)[0]
    if "default_branch()" in dw_body:
        offenders.append("presenter.default_warehouse cae en default_branch (§5.4)")
    assert offenders == [], (
        "Identidad/ámbito fabricado en la UI de inventario (§5.4):\n"
        + "\n".join(offenders))


def test_authorization_module_has_no_silent_allow_on_null_checker():
    """La rama `self._checker is None` de `require` debe lanzar, no `return`."""
    src = (_USE_CASES_DIR / "authorization.py").read_text(encoding="utf-8")
    # Aísla el cuerpo de require() y verifica que la rama None levanta.
    require_body = src.split("def require(", 1)[1]
    none_branch = require_body.split("if self._checker is None:", 1)[1]
    # Lo primero significativo tras el if debe ser un raise, no un return.
    head = "\n".join(none_branch.splitlines()[:6])
    assert "raise InventoryConfigurationError" in head
    assert "return" not in head.split("raise InventoryConfigurationError")[0]
