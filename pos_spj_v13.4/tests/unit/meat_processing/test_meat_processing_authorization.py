import pytest

from backend.application.meat_processing.authorization import (
    AllowAllMeatProcessingPermissionCheckerForTests,
    DenyAllMeatProcessingPermissionCheckerForTests,
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.domain.meat_processing.exceptions import (
    MeatProcessingConfigurationError,
    MeatProcessingPermissionDeniedError,
    MeatProcessingSegregationOfDutiesError,
)
from backend.shared.ids import new_uuid


def test_require_fails_closed_without_a_checker():
    policy = MeatProcessingAuthorizationPolicy()
    with pytest.raises(MeatProcessingConfigurationError):
        policy.require(new_uuid(), MeatProcessingPermissions.ORDER_CREATE)


def test_require_rejects_unknown_permission_code():
    policy = MeatProcessingAuthorizationPolicy.permissive_for_tests()
    with pytest.raises(MeatProcessingPermissionDeniedError):
        policy.require(new_uuid(), "PRODUCCION.no_existe")


def test_require_denies_when_checker_denies():
    policy = MeatProcessingAuthorizationPolicy(DenyAllMeatProcessingPermissionCheckerForTests())
    with pytest.raises(MeatProcessingPermissionDeniedError):
        policy.require(new_uuid(), MeatProcessingPermissions.ORDER_CREATE)


def test_require_allows_when_checker_allows():
    policy = MeatProcessingAuthorizationPolicy.permissive_for_tests()
    policy.require(new_uuid(), MeatProcessingPermissions.ORDER_CREATE)


def test_has_permission_is_non_raising_probe():
    policy = MeatProcessingAuthorizationPolicy()
    assert policy.has_permission(new_uuid(), MeatProcessingPermissions.ORDER_CREATE) is False
    permissive = MeatProcessingAuthorizationPolicy.permissive_for_tests()
    assert permissive.has_permission(new_uuid(), MeatProcessingPermissions.ORDER_CREATE) is True


def test_authorize_exception_requires_distinct_requester_and_authorizer():
    policy = MeatProcessingAuthorizationPolicy(AllowAllMeatProcessingPermissionCheckerForTests())
    same_user = new_uuid()
    with pytest.raises(MeatProcessingSegregationOfDutiesError):
        policy.authorize_exception(
            authorizer_user_id=same_user, requested_by=same_user,
            permission_code=MeatProcessingPermissions.CONSUMPTION_OVERRIDE,
            operation_id=new_uuid(), reason="excede tolerancia",
        )


def test_authorize_exception_returns_audit_grant():
    policy = MeatProcessingAuthorizationPolicy(AllowAllMeatProcessingPermissionCheckerForTests())
    grant = policy.authorize_exception(
        authorizer_user_id=new_uuid(), requested_by=new_uuid(),
        permission_code=MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE,
        operation_id=new_uuid(), reason="báscula inestable",
    )
    assert grant.permission_code == MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE
    assert grant.reason == "báscula inestable"
