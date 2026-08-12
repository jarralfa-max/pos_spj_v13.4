from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.session_authorization import (
    MeatProcessingSessionPermissionChecker,
)


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def tiene_permiso(self, code):
        return code == MeatProcessingPermissions.ORDER_VIEW


def test_live_session_requires_active_matching_actor_branch_and_permission():
    checker = MeatProcessingSessionPermissionChecker(Session())
    assert checker.has_permission("user-1", MeatProcessingPermissions.ORDER_VIEW)
    assert not checker.has_permission("other", MeatProcessingPermissions.ORDER_VIEW)
    assert not checker.has_permission("user-1", MeatProcessingPermissions.ORDER_CLOSE)


def test_inactive_or_branchless_session_denies():
    inactive = Session()
    inactive.is_active = False
    assert not MeatProcessingSessionPermissionChecker(inactive).has_permission(
        "user-1", MeatProcessingPermissions.ORDER_VIEW)
    branchless = Session()
    branchless.active_branch_id = ""
    assert not MeatProcessingSessionPermissionChecker(branchless).has_permission(
        "user-1", MeatProcessingPermissions.ORDER_VIEW)


def test_none_session_denies():
    assert not MeatProcessingSessionPermissionChecker(None).has_permission(
        "user-1", MeatProcessingPermissions.ORDER_VIEW)
