"""CRM-2 — CRM (leads/opportunities/cases) security application tests.

Covers granular permissions and the OWN/TEAM data-scope resolver shared by
leads, opportunities and service cases. Pure application — no DB.
"""

from __future__ import annotations

import pytest

from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import (
    ALL_CRM_PERMISSIONS,
    CASE_VIEW_SCOPE_PERMISSIONS,
    LEAD_VIEW_SCOPE_PERMISSIONS,
    OPPORTUNITY_VIEW_SCOPE_PERMISSIONS,
    CRMPermissions,
)
from backend.domain.crm.exceptions import CRMConfigurationError, CRMScopeError


class _StaticChecker:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self._granted


class TestCRMPermissions:
    def test_catalog_is_granular_not_broad(self):
        assert "CRM" not in ALL_CRM_PERMISSIONS
        assert len(ALL_CRM_PERMISSIONS) >= 50

    def test_all_codes_are_prefixed_strings(self):
        for code in ALL_CRM_PERMISSIONS:
            assert isinstance(code, str) and code.startswith("CRM.")

    def test_no_duplicate_codes(self):
        values = [v for k, v in vars(CRMPermissions).items()
                  if not k.startswith("_") and isinstance(v, str)]
        assert len(values) == len(set(values))

    @pytest.mark.parametrize("scope_permissions", [
        LEAD_VIEW_SCOPE_PERMISSIONS,
        OPPORTUNITY_VIEW_SCOPE_PERMISSIONS,
        CASE_VIEW_SCOPE_PERMISSIONS,
    ])
    def test_scope_axes_are_own_team_branch_company(self, scope_permissions):
        assert [axis for axis, _ in scope_permissions] == ["OWN", "TEAM", "BRANCH", "COMPANY"]


class TestCRMDataScopeResolver:
    def test_no_checker_is_fail_closed(self):
        resolver = CRMDataScopeResolver(None)
        with pytest.raises(CRMConfigurationError):
            resolver.resolve_view_scope(
                CRMScopeContext(user_id="u1"), LEAD_VIEW_SCOPE_PERMISSIONS)

    def test_no_granted_scope_is_denied(self):
        resolver = CRMDataScopeResolver(_StaticChecker(set()))
        with pytest.raises(CRMScopeError):
            resolver.resolve_view_scope(
                CRMScopeContext(user_id="u1"), OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)

    def test_own_scope_for_leads(self):
        checker = _StaticChecker({CRMPermissions.LEADS_VIEW_OWN})
        resolver = CRMDataScopeResolver(checker)
        scope = resolver.resolve_view_scope(
            CRMScopeContext(user_id="u1"), LEAD_VIEW_SCOPE_PERMISSIONS)
        assert scope == CRMDataScope(axis="OWN", owner_user_id="u1")

    def test_team_scope_for_cases_wins_over_own(self):
        checker = _StaticChecker({
            CRMPermissions.CASES_VIEW_OWN, CRMPermissions.CASES_VIEW_TEAM,
        })
        resolver = CRMDataScopeResolver(checker)
        scope = resolver.resolve_view_scope(
            CRMScopeContext(user_id="u1", team_member_ids=("u1", "u2")),
            CASE_VIEW_SCOPE_PERMISSIONS,
        )
        assert scope.axis == "TEAM"
        assert scope.team_member_ids == ("u1", "u2")

    def test_branch_scope_uses_the_session_branch(self):
        """CRM-43: el gerente ve toda su sucursal."""
        checker = _StaticChecker({CRMPermissions.LEADS_VIEW_OWN,
                                  CRMPermissions.LEADS_VIEW_BRANCH})
        scope = CRMDataScopeResolver(checker).resolve_view_scope(
            CRMScopeContext(user_id="u1", branch_ids=("b1",)), LEAD_VIEW_SCOPE_PERMISSIONS)
        assert scope == CRMDataScope(axis="BRANCH", branch_ids=("b1",))
        assert scope.includes(responsible_user_id="otro", branch_id="b1")
        assert not scope.includes(responsible_user_id="u1", branch_id="b2")

    def test_branch_scope_without_active_branch_falls_back_to_narrower(self):
        checker = _StaticChecker({CRMPermissions.LEADS_VIEW_OWN,
                                  CRMPermissions.LEADS_VIEW_BRANCH})
        scope = CRMDataScopeResolver(checker).resolve_view_scope(
            CRMScopeContext(user_id="u1"), LEAD_VIEW_SCOPE_PERMISSIONS)
        assert scope.axis == "OWN"

    def test_company_scope_sees_everything(self):
        checker = _StaticChecker({CRMPermissions.CASES_VIEW_COMPANY})
        scope = CRMDataScopeResolver(checker).resolve_view_scope(
            CRMScopeContext(user_id="u1"), CASE_VIEW_SCOPE_PERMISSIONS)
        assert scope.axis == "COMPANY"
        assert scope.includes(responsible_user_id=None, branch_id=None)

    def test_own_scope_includes_unassigned_records_the_user_created(self):
        """CRM-43: un prospecto recién creado (sin responsable) no aparecía en
        ningún directorio — ni siquiera en el de quien lo dio de alta."""
        scope = CRMDataScope(axis="OWN", owner_user_id="u1")
        assert scope.includes(responsible_user_id=None, created_by_user_id="u1")
        assert not scope.includes(responsible_user_id=None, created_by_user_id="u2")
        assert not scope.includes(responsible_user_id="u2", created_by_user_id="u1")

    def test_opportunity_scope_is_independent_from_lead_scope(self):
        # Grant only opportunity-team, not lead-anything.
        checker = _StaticChecker({CRMPermissions.OPPORTUNITIES_VIEW_TEAM})
        resolver = CRMDataScopeResolver(checker)
        with pytest.raises(CRMScopeError):
            resolver.resolve_view_scope(
                CRMScopeContext(user_id="u1"), LEAD_VIEW_SCOPE_PERMISSIONS)
        scope = resolver.resolve_view_scope(
            CRMScopeContext(user_id="u1"), OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        assert scope.axis == "TEAM"
