from decimal import Decimal
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError,
    CashConfigurationError,
    CashLimitExceededError,
    CashPermissionDeniedError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import (
    CashLimitDecision,
    CashMonetaryLimitPolicy,
    CashSegregationOfDutiesPolicy,
)


class _Permissions:
    def __init__(self, grants=()):
        self.grants = set(grants)

    def has_permission(self, user_id, permission_code):
        return (user_id, permission_code) in self.grants


class _Scopes:
    def __init__(self, grants=()):
        self.grants = set(grants)

    def can_access_branch(self, *, user_id, branch_id):
        return (user_id, branch_id) in self.grants


class _Audit:
    def __init__(self):
        self.grants = []
        self.entries = []

    def record_hot_authorization(self, grant):
        self.grants.append(grant)

    def record_security_audit(self, entry):
        self.entries.append(entry)


class CashRegisterSecurityTests(unittest.TestCase):
    def test_catalog_is_granular_and_has_no_legacy_general_action(self):
        self.assertEqual(CashPermissions.SHIFT_OPEN, "CAJA.turno.abrir")
        self.assertEqual(CashPermissions.BLIND_COUNT_CONFIRM, "CAJA.conteo.confirmar")
        self.assertEqual(CashPermissions.DIFFERENCE_RESOLVE, "CAJA.diferencia.resolver")
        self.assertFalse(hasattr(CashPermissions, "GENERAL"))

    def test_authorization_fails_closed_and_revalidates_branch_scope(self):
        with self.assertRaises(CashConfigurationError):
            CashAuthorizationPolicy().require(
                user_id="cashier", permission_code=CashPermissions.SHIFT_OPEN,
                branch_id="branch-a")

        policy = CashAuthorizationPolicy(
            permissions=_Permissions({("cashier", CashPermissions.SHIFT_OPEN)}),
            scopes=_Scopes({("cashier", "branch-a")}),
        )
        policy.require(user_id="cashier", permission_code=CashPermissions.SHIFT_OPEN,
                       branch_id="branch-a")
        with self.assertRaises(CashPermissionDeniedError):
            policy.require(user_id="cashier", permission_code=CashPermissions.SHIFT_OPEN,
                           branch_id="branch-b")
        with self.assertRaises(CashPermissionDeniedError):
            policy.require(user_id="cashier", permission_code="CAJA")

    def test_decimal_limits_have_threshold_hard_cap_and_no_float(self):
        policy = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("500.00"), hard_cap=Decimal("2000.00"))
        self.assertIs(policy.evaluate(Decimal("500.00")), CashLimitDecision.WITHIN)
        self.assertIs(policy.evaluate(Decimal("500.01")), CashLimitDecision.REQUIRES_AUTHORIZATION)
        self.assertIs(policy.evaluate(Decimal("2000.01")), CashLimitDecision.EXCEEDS_HARD_CAP)
        with self.assertRaises(TypeError):
            policy.evaluate(10.0)
        with self.assertRaises(CashLimitExceededError):
            policy.require_operable(Decimal("2000.01"))

    def test_segregation_protects_count_cut_difference_handover_and_refund(self):
        policy = CashSegregationOfDutiesPolicy()
        with self.assertRaises(CashSegregationOfDutiesError):
            policy.counter_cannot_review_own_difference("u1", "u1")
        with self.assertRaises(CashSegregationOfDutiesError):
            policy.z_cut_creator_cannot_resolve_difference("u1", "u1")
        with self.assertRaises(CashSegregationOfDutiesError):
            policy.handover_requires_distinct_parties("u1", "u1")
        with self.assertRaises(CashSegregationOfDutiesError):
            policy.refund_requester_requires_independent_authorizer("u1", "u1")

    def test_hot_authorization_is_independent_scoped_and_audited(self):
        audit = _Audit()
        policy = CashAuthorizationPolicy(
            permissions=_Permissions({("manager", CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT)}),
            scopes=_Scopes({("manager", "branch-a")}), audit_sink=audit)
        grant = policy.authorize_exception(
            requested_by="cashier", authorized_by="manager",
            permission_code=CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
            reason="Retiro de seguridad validado", operation_id="operation-1",
            entity_id="shift-1", branch_id="branch-a", amount=Decimal("750.00"),
            device_id="terminal-1")
        self.assertEqual(audit.grants, [grant])
        self.assertEqual(audit.entries[0].authorization_id, grant.id)
        self.assertNotEqual(grant.id, grant.operation_id)
        with self.assertRaises(CashAuthorizationRequiredError):
            policy.authorize_exception(
                requested_by="manager", authorized_by="manager",
                permission_code=CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
                reason="auto", operation_id="operation-2", entity_id="shift-1",
                branch_id="branch-a", amount=Decimal("750.00"))


if __name__ == "__main__":
    unittest.main()
