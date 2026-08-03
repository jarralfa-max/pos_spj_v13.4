from backend.application.losses.permissions import LossPermissions
from backend.application.losses.session_authorization import LossSessionPermissionChecker


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def tiene_permiso(self, code):
        return code == LossPermissions.REPORT


def test_live_session_requires_active_matching_actor_branch_and_permission():
    checker = LossSessionPermissionChecker(Session())
    assert checker.has_permission("user-1", LossPermissions.REPORT)
    assert not checker.has_permission("other", LossPermissions.REPORT)
    assert not checker.has_permission("user-1", LossPermissions.APPROVE)


def test_inactive_or_branchless_session_denies():
    inactive = Session()
    inactive.is_active = False
    assert not LossSessionPermissionChecker(inactive).has_permission(
        "user-1", LossPermissions.REPORT)
    branchless = Session()
    branchless.active_branch_id = ""
    assert not LossSessionPermissionChecker(branchless).has_permission(
        "user-1", LossPermissions.REPORT)
