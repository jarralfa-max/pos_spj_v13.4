"""P0-A slice 2 (§5.2) — composition root + real session RBAC checker.

- `InventoryUseCaseFactory` requires a real PermissionChecker (fail closed).
- It builds sensitive use cases wired with the checker-backed policy, not the
  permissive default.
- `InventorySessionPermissionChecker` bridges canonical INVENTORY_* codes to the
  live legacy `inventario.*` roles and denies without a session.
"""

import pytest

from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    DenyAllInventoryPermissionCheckerForTests,
)
from backend.application.inventory.composition import InventoryUseCaseFactory
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.session_authorization import (
    InventorySessionPermissionChecker,
    legacy_codes_for,
)
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.exceptions import (
    InventoryConfigurationError,
    InventoryPermissionDeniedError,
)


# ── factory fail-closed ──────────────────────────────────────────────────────
def test_factory_requires_a_checker():
    with pytest.raises(InventoryConfigurationError):
        InventoryUseCaseFactory(permission_checker=None)


def test_factory_builds_use_case_wired_with_checker():
    factory = InventoryUseCaseFactory(
        permission_checker=DenyAllInventoryPermissionCheckerForTests())
    uc = factory.post_movement()
    assert isinstance(uc, PostInventoryMovementUseCase)
    # The wired policy denies (checker-backed), proving it is NOT the permissive
    # default that would silently allow.
    with pytest.raises(InventoryPermissionDeniedError):
        factory.authorization_policy.require(
            "u1", InventoryPermissions.MOVEMENT_CREATE)


def test_factory_for_tests_allows():
    factory = InventoryUseCaseFactory.for_tests()
    assert isinstance(factory._checker,  # noqa: SLF001 — intención de prueba
                      AllowAllInventoryPermissionCheckerForTests)
    factory.authorization_policy.require("u1", InventoryPermissions.MOVEMENT_CREATE)


def test_generic_build_injects_policy():
    factory = InventoryUseCaseFactory.for_tests()
    uc = factory.build(PostInventoryMovementUseCase)
    assert isinstance(uc, PostInventoryMovementUseCase)


# ── session checker ──────────────────────────────────────────────────────────
class _Session:
    def __init__(self, user_id, codes):
        self.user_id = user_id
        self._codes = set(codes)

    def tiene_permiso(self, code):
        return code in self._codes


def test_session_checker_denies_without_session():
    checker = InventorySessionPermissionChecker(None)
    assert checker.has_permission("u1", InventoryPermissions.MOVEMENT_CREATE) is False


def test_session_checker_grants_via_legacy_edit():
    checker = InventorySessionPermissionChecker(_Session("u1", {"inventario.editar"}))
    assert checker.has_permission("u1", InventoryPermissions.MOVEMENT_CREATE) is True


def test_session_checker_view_permission_not_granted_by_view_for_mutation():
    checker = InventorySessionPermissionChecker(_Session("u1", {"inventario.ver"}))
    # A mutation is NOT granted by read-only legacy access.
    assert checker.has_permission("u1", InventoryPermissions.MOVEMENT_CREATE) is False


def test_session_checker_user_mismatch_denies():
    checker = InventorySessionPermissionChecker(_Session("boss", {"inventario.editar"}))
    assert checker.has_permission("clerk", InventoryPermissions.MOVEMENT_CREATE) is False


def test_session_checker_grants_canonical_code_directly():
    checker = InventorySessionPermissionChecker(
        _Session("u1", {InventoryPermissions.MOVEMENT_CREATE}))
    assert checker.has_permission("u1", InventoryPermissions.MOVEMENT_CREATE) is True


def test_legacy_bridge_maps_by_action():
    assert legacy_codes_for("INVENTORY_MOVEMENT_VIEW") == ("inventario.ver",)
    assert "inventario.ajustar" in legacy_codes_for("INVENTORY_ADJUSTMENT_CREATE")
    assert "inventario.transferir" in legacy_codes_for("INVENTORY_TRANSFER_DISPATCH")
    assert legacy_codes_for("INVENTORY_MOVEMENT_CREATE") == ("inventario.editar",)
