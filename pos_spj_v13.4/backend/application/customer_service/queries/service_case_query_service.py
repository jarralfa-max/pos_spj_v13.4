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

from dataclasses import dataclass, field

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CASE_VIEW_SCOPE_PERMISSIONS, CRMPermissions
from backend.domain.crm.exceptions import CRMPermissionDeniedError, CRMScopeError
from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.exceptions import ServiceCaseNotFoundError
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


@dataclass(frozen=True)
class ServiceCaseRow:
    """§86: un caso con su SLA (puede no tener: ninguna política coincidió)."""

    case: CustomerServiceCase
    sla: SLAInstance | None


@dataclass(frozen=True)
class ServiceCaseDetail:
    case: CustomerServiceCase
    sla: SLAInstance | None
    escalations: list = field(default_factory=list)
    resolution: object | None = None


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
        cases = self._uow.cases.list_in_scope(scope, limit=limit, offset=offset)
        can_view_sensitive = self._auth.has_permission(context.user_id,
                                                        CRMPermissions.CASES_VIEW_SENSITIVE)
        return [c for c in cases if not c.is_sensitive or can_view_sensitive]

    def list_for_customer(self, customer_id: str, context: CRMScopeContext, *,
                          limit: int = 200) -> list[CustomerServiceCase]:
        """CRM-12: Customer 360's "casos" tab. Fetches by customer_id (not
        assignee) then filters through the caller's resolved scope and
        sensitive-case masking, same as ``list_directory``."""
        scope = self._scope_resolver.resolve_view_scope(context, CASE_VIEW_SCOPE_PERMISSIONS)
        cases = self._uow.cases.list_for_customer(customer_id, limit=limit)
        can_view_sensitive = self._auth.has_permission(context.user_id,
                                                        CRMPermissions.CASES_VIEW_SENSITIVE)
        return [c for c in cases if self._in_scope(c, scope)
                and (not c.is_sensitive or can_view_sensitive)]

    @staticmethod
    def _in_scope(case: CustomerServiceCase, scope: CRMDataScope) -> bool:
        return scope.includes(responsible_user_id=case.assigned_user_id,
                              created_by_user_id=case.created_by_user_id,
                              branch_id=case.origin_branch_id)

    def list_rows(self, context: CRMScopeContext, *, limit: int = 500) -> list[ServiceCaseRow]:
        """CRM-43: la bandeja de casos con el SLA de cada uno."""
        return [ServiceCaseRow(c, self._uow.sla_instances.get_for_case(c.id))
                for c in self.list_directory(context, limit=limit)]

    def get_detail(self, case_id: str, context: CRMScopeContext) -> ServiceCaseDetail:
        case = self.get_profile(case_id, context)
        return ServiceCaseDetail(
            case=case, sla=self._uow.sla_instances.get_for_case(case_id),
            escalations=self._uow.escalations.list_for_case(case_id),
            resolution=self._uow.resolutions.get_for_case(case_id))
