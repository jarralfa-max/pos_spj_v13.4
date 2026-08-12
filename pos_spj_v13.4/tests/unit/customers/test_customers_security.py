"""CRM-2 — Customer Master security domain/application tests.

Covers granular permissions, the OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/COMPANY
data-scope resolver, segregation of duties, the hot-authorization grant, the
audit entry, and field-level masking. Pure domain/application — no DB.
"""

from __future__ import annotations

import pytest

from backend.application.customers.data_scope import (
    CustomerDataScopeResolver,
    CustomerScopeContext,
)
from backend.application.customers.permissions import (
    ALL_CUSTOMER_PERMISSIONS,
    CUSTOMER_VIEW_SCOPE_PERMISSIONS,
    CustomerPermissions,
)
from backend.application.customers.role_matrix import CRM_ROLE_MATRIX
from backend.domain.customers.exceptions import (
    CustomerConfigurationError,
    CustomerScopeError,
    CustomerSegregationOfDutiesError,
    InvalidAuthorizationError,
)
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.domain.customers.value_objects.audit_entry import CustomerAuditEntry
from backend.domain.customers.value_objects.authorization_grant import (
    CustomerAuthorizationGrant,
)
from backend.domain.customers.value_objects.field_visibility import (
    FieldVisibility,
    is_sensitive_field,
    mask,
)


class _StaticChecker:
    """Grants exactly the permission codes it was constructed with."""

    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self._granted


# ── permisos granulares ────────────────────────────────────────────────────
class TestCustomerPermissions:
    def test_catalog_is_granular_not_broad(self):
        assert "CLIENTES" not in ALL_CUSTOMER_PERMISSIONS
        assert len(ALL_CUSTOMER_PERMISSIONS) >= 50

    def test_all_codes_are_prefixed_strings(self):
        for code in ALL_CUSTOMER_PERMISSIONS:
            assert isinstance(code, str) and code.startswith("CLIENTES.")

    def test_no_duplicate_codes(self):
        values = [v for k, v in vars(CustomerPermissions).items()
                  if not k.startswith("_") and isinstance(v, str)]
        assert len(values) == len(set(values))

    def test_scope_axes_are_all_present_and_ordered_own_to_company(self):
        axes = [axis for axis, _ in CUSTOMER_VIEW_SCOPE_PERMISSIONS]
        assert axes == ["OWN", "TEAM", "BRANCH", "TERRITORY", "PORTFOLIO", "COMPANY"]

    def test_key_sensitive_actions_present(self):
        for code in (
            CustomerPermissions.CREDIT_APPROVE,
            CustomerPermissions.ANONYMIZE,
            CustomerPermissions.DUPLICATES_MERGE,
            CustomerPermissions.SENSITIVE_DATA_UNMASK,
        ):
            assert code in ALL_CUSTOMER_PERMISSIONS


# ── alcance de datos (scopes) ───────────────────────────────────────────────
class TestCustomerDataScopeResolver:
    def test_no_checker_is_fail_closed(self):
        resolver = CustomerDataScopeResolver(None)
        with pytest.raises(CustomerConfigurationError):
            resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))

    def test_no_user_id_is_denied(self):
        resolver = CustomerDataScopeResolver(_StaticChecker({CustomerPermissions.VIEW_OWN}))
        with pytest.raises(CustomerScopeError):
            resolver.resolve_view_scope(CustomerScopeContext(user_id=""))

    def test_no_granted_scope_is_denied(self):
        resolver = CustomerDataScopeResolver(_StaticChecker(set()))
        with pytest.raises(CustomerScopeError):
            resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))

    def test_own_scope(self):
        resolver = CustomerDataScopeResolver(_StaticChecker({CustomerPermissions.VIEW_OWN}))
        scope = resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))
        assert scope.axis == "OWN"
        assert scope.owner_user_id == "u1"

    def test_team_scope_defaults_team_to_self(self):
        resolver = CustomerDataScopeResolver(_StaticChecker({CustomerPermissions.VIEW_TEAM}))
        scope = resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))
        assert scope.axis == "TEAM"
        assert scope.team_member_ids == ("u1",)

    def test_branch_scope_requires_branch_in_context(self):
        resolver = CustomerDataScopeResolver(_StaticChecker({CustomerPermissions.VIEW_BRANCH}))
        with pytest.raises(CustomerConfigurationError):
            resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))
        scope = resolver.resolve_view_scope(
            CustomerScopeContext(user_id="u1", branch_id="suc-1"))
        assert scope.axis == "BRANCH" and scope.branch_id == "suc-1"

    def test_widest_granted_scope_wins(self):
        # Un usuario con ver.propia Y ver.compania obtiene COMPANY (sin filtro).
        checker = _StaticChecker({CustomerPermissions.VIEW_OWN, CustomerPermissions.VIEW_COMPANY})
        resolver = CustomerDataScopeResolver(checker)
        scope = resolver.resolve_view_scope(CustomerScopeContext(user_id="u1"))
        assert scope.axis == "COMPANY"
        assert scope.owner_user_id is None


# ── segregación de funciones (§73) ──────────────────────────────────────────
class TestCustomerSegregationOfDuties:
    def setup_method(self):
        self.policy = CustomerSegregationOfDutiesPolicy()

    def test_credit_requester_cannot_self_approve(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_credit_requester_not_self_approving("u1", "u1")
        self.policy.enforce_credit_requester_not_self_approving("u1", "u2")  # no raise

    def test_merge_proposer_cannot_self_approve(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_merge_proposer_not_self_approving("u1", "u1")

    def test_sensitive_import_approver_must_be_distinct(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_sensitive_import_approver_distinct("u1", "u1", is_sensitive=True)
        # A non-sensitive import doesn't require a second approver.
        self.policy.enforce_sensitive_import_approver_distinct("u1", "u1", is_sensitive=False)

    def test_ownership_reassignment_requires_reason(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_ownership_reassignment_justified("")
        self.policy.enforce_ownership_reassignment_justified("cartera rebalanceada")

    def test_sensitive_export_requires_evidence(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_sensitive_export_evidenced("   ")

    def test_anonymization_must_preserve_audit(self):
        with pytest.raises(CustomerSegregationOfDutiesError):
            self.policy.enforce_anonymization_preserves_audit(False)
        self.policy.enforce_anonymization_preserves_audit(True)


# ── autorización en caliente (§74) ──────────────────────────────────────────
class TestCustomerAuthorizationGrant:
    def test_requires_distinct_requester_and_authorizer(self):
        with pytest.raises(InvalidAuthorizationError):
            CustomerAuthorizationGrant(
                permission_code=CustomerPermissions.CREDIT_LIMIT_OVERRIDE,
                requested_by="u1", authorized_by="u1",
                operation_id="op-1", reason="límite excepcional",
            )

    def test_requires_reason(self):
        with pytest.raises(InvalidAuthorizationError):
            CustomerAuthorizationGrant(
                permission_code=CustomerPermissions.CREDIT_LIMIT_OVERRIDE,
                requested_by="u1", authorized_by="u2",
                operation_id="op-1", reason="   ",
            )

    def test_valid_grant_coerces_amount_to_decimal(self):
        grant = CustomerAuthorizationGrant(
            permission_code=CustomerPermissions.CREDIT_LIMIT_OVERRIDE,
            requested_by="u1", authorized_by="u2",
            operation_id="op-1", reason="cliente estratégico",
            credit_amount="15000.50",
        )
        from decimal import Decimal
        assert grant.credit_amount == Decimal("15000.50")

    def test_float_amount_is_rejected(self):
        with pytest.raises(InvalidAuthorizationError):
            CustomerAuthorizationGrant(
                permission_code=CustomerPermissions.CREDIT_LIMIT_OVERRIDE,
                requested_by="u1", authorized_by="u2",
                operation_id="op-1", reason="motivo",
                credit_amount=15000.5,
            )


# ── auditoría (§76) ──────────────────────────────────────────────────────────
class TestCustomerAuditEntry:
    def test_requires_core_fields(self):
        with pytest.raises(InvalidAuthorizationError):
            CustomerAuditEntry(
                action="", entity_type="customer", entity_id="c1",
                user_id="u1", operation_id="op-1",
            )

    def test_valid_entry_has_id_and_timestamp(self):
        entry = CustomerAuditEntry(
            action="ANONYMIZE", entity_type="customer", entity_id="c1",
            user_id="u1", operation_id="op-1", customer_id="c1",
            correlation_id="corr-1", workstation_id="ws-1",
        )
        assert entry.id and entry.occurred_at


# ── enmascaramiento (§75) ────────────────────────────────────────────────────
class TestFieldVisibility:
    def test_is_sensitive_field(self):
        assert is_sensitive_field("telefono")
        assert is_sensitive_field("EMAIL")
        assert not is_sensitive_field("nombre")

    def test_masked_hides_everything(self):
        assert mask("5512345678", FieldVisibility.MASKED) == "•" * 10

    def test_partially_visible_reveals_only_tail(self):
        assert mask("5512345678", FieldVisibility.PARTIALLY_VISIBLE) == "••••••5678"

    def test_visible_returns_unchanged(self):
        assert mask("5512345678", FieldVisibility.VISIBLE) == "5512345678"

    def test_restricted_returns_empty(self):
        assert mask("5512345678", FieldVisibility.RESTRICTED) == ""

    def test_never_raises_on_empty_value(self):
        assert mask("", FieldVisibility.PARTIALLY_VISIBLE) == ""


# ── matriz de roles (§59, §72) ──────────────────────────────────────────────
class TestCRMRoleMatrix:
    def test_every_role_code_is_a_known_permission(self):
        from backend.application.crm.permissions import ALL_CRM_PERMISSIONS
        known = ALL_CUSTOMER_PERMISSIONS | ALL_CRM_PERMISSIONS
        for role, codes in CRM_ROLE_MATRIX.items():
            unknown = [c for c in codes if c not in known]
            assert not unknown, f"{role} grants unknown code(s): {unknown}"

    def test_credit_analyst_cannot_approve_credit(self):
        assert CustomerPermissions.CREDIT_APPROVE not in CRM_ROLE_MATRIX["CRM_CREDIT_ANALYST"]

    def test_auditor_has_no_mutating_permissions(self):
        mutating = {
            CustomerPermissions.CREATE, CustomerPermissions.EDIT,
            CustomerPermissions.CREDIT_APPROVE, CustomerPermissions.ANONYMIZE,
            CustomerPermissions.DUPLICATES_MERGE,
        }
        assert not (set(CRM_ROLE_MATRIX["CRM_AUDITOR"]) & mutating)

    def test_data_steward_cannot_self_approve_sensitive_import(self):
        assert CustomerPermissions.IMPORT_APPROVE not in CRM_ROLE_MATRIX["CRM_DATA_STEWARD"]
