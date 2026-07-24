from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.permissions import TransferPermissions
from backend.domain.transfers.exceptions import (PermissionDeniedError, SegregationOfDutiesError,
                                                 TransferAuthorizationRequiredError, TransferLimitExceededError)
from backend.domain.transfers.policies.segregation_of_duties_policy import TransferSegregationOfDutiesPolicy
from backend.domain.transfers.policies.transfer_limit_policy import TransferLimitPolicy


class _Permissions:
    def __init__(self, allowed: set[tuple[str, str]]): self.allowed = allowed
    def has_permission(self, user_id, permission_code): return (user_id, permission_code) in self.allowed


class _Scopes:
    def __init__(self, allowed_branches: set[str]): self.allowed_branches = allowed_branches
    def can_access_transfer_scope(self, *, user_id, branch_id, warehouse_id, location_id): return branch_id in self.allowed_branches


class _Audit:
    def __init__(self): self.grants = []
    def record_hot_authorization(self, grant): self.grants.append(grant)


def test_backend_revalidates_permission_and_scope():
    policy = TransferAuthorizationPolicy(_Permissions({("dispatcher", TransferPermissions.DISPATCH)}), _Scopes({"branch-a"}))
    policy.require(user_id="dispatcher", permission_code=TransferPermissions.DISPATCH, branch_id="branch-a")
    with pytest.raises(PermissionDeniedError):
        policy.require(user_id="dispatcher", permission_code=TransferPermissions.DISPATCH, branch_id="branch-b")
    with pytest.raises(PermissionDeniedError):
        policy.require(user_id="receiver", permission_code=TransferPermissions.DISPATCH, branch_id="branch-a")


def test_hot_authorization_requires_another_authorized_user_and_is_audited():
    audit = _Audit()
    policy = TransferAuthorizationPolicy(_Permissions({("manager", TransferPermissions.RECEIVE_OVER_TOLERANCE)}), audit_sink=audit)
    grant = policy.authorize_exception(requested_by="receiver", authorized_by="manager", permission_code=TransferPermissions.RECEIVE_OVER_TOLERANCE, reason="Conteo validado", operation_id="operation", transfer_id="transfer", quantity=Decimal("2"), device_id="device")
    assert audit.grants == [grant]
    assert grant.quantity == Decimal("2")
    with pytest.raises(TransferAuthorizationRequiredError):
        policy.authorize_exception(requested_by="receiver", authorized_by="receiver", permission_code=TransferPermissions.RECEIVE_OVER_TOLERANCE, reason="auto", operation_id="other", transfer_id="transfer")


def test_segregation_and_configuration_limits_are_enforced():
    segregation = TransferSegregationOfDutiesPolicy()
    with pytest.raises(SegregationOfDutiesError): segregation.requester_cannot_approve("requester", "requester", elevated=True)
    with pytest.raises(SegregationOfDutiesError): segregation.dispatcher_cannot_receive("dispatcher", "dispatcher")
    with pytest.raises(SegregationOfDutiesError): segregation.difference_reporter_cannot_resolve("receiver", "receiver", critical=True)
    with pytest.raises(SegregationOfDutiesError): segregation.custody_handover_requires_distinct_parties("carrier", "carrier")
    limits = TransferLimitPolicy(max_quantity=Decimal("10"), max_weight=Decimal("100"), max_reference_value=Decimal("500"))
    limits.require_within_limits(quantity=Decimal("10"), weight=Decimal("100"), reference_value=Decimal("500"))
    with pytest.raises(TransferLimitExceededError): limits.require_within_limits(quantity=Decimal("11"), weight=Decimal("0"))
