"""CustomerSessionPermissionChecker — the real PermissionChecker the
customers_crm composition root wires into CustomerAuthorizationPolicy/
CRMAuthorizationPolicy. Mirrors tests/unit/inventory/test_inventory_role_matrix.py's
`_Session` fake and fail-closed assertions for InventorySessionPermissionChecker.
"""

from __future__ import annotations

from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.session_authorization import (
    CustomerSessionPermissionChecker,
)


class _Session:
    def __init__(self, grants, *, is_active=True, active_branch_id="branch-1",
                 user_id="u1"):
        self._grants = set(grants)
        self.is_active = is_active
        self.active_branch_id = active_branch_id
        self.user_id = user_id

    def tiene_permiso(self, code):
        return code in self._grants


def test_grants_when_session_active_matches_user_and_has_permission():
    session = _Session({CustomerPermissions.VIEW})
    checker = CustomerSessionPermissionChecker(session)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is True


def test_denies_when_permission_not_granted():
    session = _Session(set())
    checker = CustomerSessionPermissionChecker(session)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is False


def test_denies_when_session_inactive_despite_grant():
    session = _Session({CustomerPermissions.VIEW}, is_active=False)
    checker = CustomerSessionPermissionChecker(session)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is False


def test_denies_when_no_active_branch_despite_grant():
    session = _Session({CustomerPermissions.VIEW}, active_branch_id="")
    checker = CustomerSessionPermissionChecker(session)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is False


def test_denies_when_requested_user_id_does_not_match_session_user():
    session = _Session({CustomerPermissions.VIEW}, user_id="other-user")
    checker = CustomerSessionPermissionChecker(session)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is False


def test_denies_when_session_is_none():
    checker = CustomerSessionPermissionChecker(None)
    assert checker.has_permission("u1", CustomerPermissions.VIEW) is False
