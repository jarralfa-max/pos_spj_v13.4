"""ServiceCaseQueryService — read side for Service Cases. Reads only;
never mutates. Reuses CRM-2's ``CRMDataScopeResolver`` +
``CASE_VIEW_SCOPE_PERMISSIONS`` directly (OWN/TEAM axes were already
defined for cases, unlike Activities/Tasks/Notes in CRM-6) — same
cross-package reuse as the rest of this bounded context's authorization.

Sensitive cases (``is_sensitive``) are masked out of directory results and
denied on direct ``get()`` unless the caller also holds
``CASES_VIEW_SENSITIVE`` — mirrors CRMNoteQueryService's private-note
masking (CRM-6) and CRM-2's ``FieldVisibility`` precedent.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CASE_VIEW_SCOPE_PERMISSIONS, CRMPermissions
from backend.domain.crm.exceptions import CRMPermissionDeniedError, CRMScopeError
from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.exceptions import ServiceCaseNotFoundError
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


class ServiceCaseQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver,
                 authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerServiceUnitOfWork(connection)
        self._scope_resolver = scope_resolver
        self._auth = authorization or CRMAuthorizationPolicy()

    def get_profile(self, case_id: str, context: CRMScopeContext) -> CustomerServiceCase:
        scope = self._scope_resolver.resolve_view_scope(context, CASE_VIEW_SCOPE_PERMISSIONS)
        case = self._uow.cases.get(case_id)
        if case is None:
            raise ServiceCaseNotFoundError(f"Caso {case_id!r} no existe")
        if not self._in_scope(case, scope):
            raise CRMScopeError(
                f"El caso {case_id!r} está fuera del alcance ({scope.axis}) del usuario")
        if case.is_sensitive and not self._auth.has_permission(
                context.user_id, CRMPermissions.CASES_VIEW_SENSITIVE):
            raise CRMPermissionDeniedError(
                f"El caso {case_id!r} es sensible; requiere {CRMPermissions.CASES_VIEW_SENSITIVE}")
        return case

    def list_directory(self, context: CRMScopeContext, *, limit: int = 200,
                        offset: int = 0) -> list[CustomerServiceCase]:
        scope = self._scope_resolver.resolve_view_scope(context, CASE_VIEW_SCOPE_PERMISSIONS)
        owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
        cases = self._uow.cases.list_owned_by(owner_ids, limit=limit, offset=offset)
        can_view_sensitive = self._auth.has_permission(context.user_id,
                                                        CRMPermissions.CASES_VIEW_SENSITIVE)
        return [c for c in cases if not c.is_sensitive or can_view_sensitive]

    @staticmethod
    def _in_scope(case: CustomerServiceCase, scope: CRMDataScope) -> bool:
        if scope.axis == "OWN":
            return case.assigned_user_id == scope.owner_user_id
        return case.assigned_user_id in scope.team_member_ids
