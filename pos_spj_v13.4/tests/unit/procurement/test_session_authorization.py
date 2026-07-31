"""Runtime procurement authorization uses the canonical live session."""

from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def tiene_permiso(self, code):
        return code == "PURCHASES_DIRECT_CREATE"


def test_live_session_requires_matching_actor_branch_and_permission():
    checker = ProcurementSessionPermissionChecker(Session())
    assert checker.has_permission("user-1", "PURCHASES_DIRECT_CREATE")
    assert not checker.has_permission("other", "PURCHASES_DIRECT_CREATE")
    assert not checker.has_permission("user-1", "PURCHASES_ORDER_APPROVE")


def test_inactive_or_branchless_session_denies():
    inactive = Session()
    inactive.is_active = False
    assert not ProcurementSessionPermissionChecker(inactive).has_permission(
        "user-1", "PURCHASES_DIRECT_CREATE")
    branchless = Session()
    branchless.active_branch_id = ""
    assert not ProcurementSessionPermissionChecker(branchless).has_permission(
        "user-1", "PURCHASES_DIRECT_CREATE")
