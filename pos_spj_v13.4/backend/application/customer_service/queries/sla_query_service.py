"""SLAQueryService — read side for SLA tracking (§30-32, dashboard KPI
"Casos fuera de SLA" per the master prompt's dashboard section). Reads
only; never mutates. Gated by the flat ``SLA_VIEW`` permission (SLA
oversight is an operational/supervisory view, not owner-scoped like cases
themselves).
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.domain.customer_service.enums import SLABreachStatus
from backend.domain.customer_service.exceptions import SLAInstanceNotFoundError
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


class SLAQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerServiceUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get_for_case(self, case_id: str, *, actor_user_id: str) -> SLAInstance:
        self._auth.require(actor_user_id, CRMPermissions.SLA_VIEW)
        sla = self._uow.sla_instances.get_for_case(case_id)
        if sla is None:
            raise SLAInstanceNotFoundError(f"El caso {case_id!r} no tiene una SLA asociada")
        return sla

    def list_breached(self, *, actor_user_id: str, as_of: str | None = None) -> list[SLAInstance]:
        self._auth.require(actor_user_id, CRMPermissions.SLA_VIEW)
        return [s for s in self._uow.sla_instances.list_open()
                if s.effective_breach_status(as_of=as_of) is SLABreachStatus.BREACHED]

    def list_at_risk(self, *, actor_user_id: str, as_of: str | None = None) -> list[SLAInstance]:
        self._auth.require(actor_user_id, CRMPermissions.SLA_VIEW)
        return [s for s in self._uow.sla_instances.list_open()
                if s.effective_breach_status(as_of=as_of) is SLABreachStatus.AT_RISK]
