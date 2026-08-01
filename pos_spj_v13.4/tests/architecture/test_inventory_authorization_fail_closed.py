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
