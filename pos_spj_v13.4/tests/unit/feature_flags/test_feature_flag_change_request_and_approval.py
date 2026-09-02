"""SET-21 — "Approval": FeatureFlagChangeRequest state machine +
feature_flag_approval_policy.assert_can_approve. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.enums import FeatureFlagChangeStatus, FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import (
    FeatureFlagApprovalRequiredError,
    FeatureFlagChangeTransitionNotAllowedError,
    FeatureFlagsInvalidValueError,
)
from backend.domain.feature_flags.policies.feature_flag_approval_policy import assert_can_approve
from backend.shared.ids import is_uuidv7, new_uuid


def _request(**overrides) -> FeatureFlagChangeRequest:
    kwargs = dict(
        flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
        proposed_enabled=True, requested_by_user_id="admin-1",
    )
    kwargs.update(overrides)
    return FeatureFlagChangeRequest.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_starts_pending(self):
        request = _request()
        assert is_uuidv7(request.id)
        assert request.status is FeatureFlagChangeStatus.PENDING_APPROVAL

    def test_requires_requested_by_user_id(self):
        with pytest.raises(FeatureFlagsInvalidValueError):
            _request(requested_by_user_id="")

    @pytest.mark.parametrize("percentage", [-1, 101, 1.5, True])
    def test_rejects_invalid_rollout_percentage(self, percentage):
        with pytest.raises(FeatureFlagsInvalidValueError):
            _request(proposed_rollout_percentage=percentage)

    def test_defaults_rollout_to_100(self):
        request = _request()
        assert request.proposed_rollout_percentage == 100


class TestApproveRejectApply:
    def test_full_happy_path(self):
        request = _request()
        request.approve(approved_by_user_id="admin-2")
        assert request.status is FeatureFlagChangeStatus.APPROVED
        assert request.approved_by_user_id == "admin-2"

        rule = request.apply()
        assert request.status is FeatureFlagChangeStatus.APPLIED
        assert rule.flag_id == request.flag_id
        assert rule.enabled is request.proposed_enabled

    def test_reject_sets_reason_and_is_terminal(self):
        request = _request()
        request.reject(reason="No autorizado")
        assert request.status is FeatureFlagChangeStatus.REJECTED
        assert request.reason == "No autorizado"

    def test_reject_requires_reason(self):
        request = _request()
        with pytest.raises(FeatureFlagsInvalidValueError):
            request.reject(reason="   ")

    def test_approve_requires_approved_by_user_id(self):
        request = _request()
        with pytest.raises(FeatureFlagsInvalidValueError):
            request.approve(approved_by_user_id="")

    def test_cannot_approve_twice(self):
        request = _request()
        request.approve(approved_by_user_id="admin-2")
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            request.approve(approved_by_user_id="admin-3")

    def test_cannot_reject_after_approval(self):
        request = _request()
        request.approve(approved_by_user_id="admin-2")
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            request.reject(reason="demasiado tarde")

    def test_cannot_apply_before_approval(self):
        request = _request()
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            request.apply()

    def test_cannot_apply_twice(self):
        request = _request()
        request.approve(approved_by_user_id="admin-2")
        request.apply()
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            request.apply()

    def test_cannot_apply_a_rejected_request(self):
        request = _request()
        request.reject(reason="No autorizado")
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            request.apply()


class TestAssertCanApprove:
    def test_requester_cannot_self_approve(self):
        request = _request(requested_by_user_id="admin-1")
        with pytest.raises(FeatureFlagApprovalRequiredError):
            assert_can_approve(request, approver_user_id="admin-1")

    def test_different_user_can_approve(self):
        request = _request(requested_by_user_id="admin-1")
        assert_can_approve(request, approver_user_id="admin-2")  # does not raise
