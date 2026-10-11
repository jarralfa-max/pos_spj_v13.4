"""CRMRecordScopeGuard (CRM-43) — alcance por registro al OPERAR.

Los permisos dicen qué acción puede hacer alguien («cerrar casos»); el alcance
dice sobre qué registros (los propios, los de su sucursal, los de toda la
empresa — matriz sembrada por la migración 314). Hasta CRM-43 el alcance sólo
filtraba las bandejas: un cajero no veía el caso de otro en su lista, pero con
el identificador podía cerrarlo igual, porque los casos de uso sólo validan el
permiso.

Este guardián se consulta antes de ejecutar cualquier comando que apunte a un
prospecto, una oportunidad, un caso o una cotización (directamente o a
través de una actividad, tarea o nota sobre ellos): el registro debe caer dentro del mismo
alcance con el que el actor lo vería en su bandeja. Las automatizaciones del
sistema no pasan por aquí: actúan como ``SYSTEM_AUTOMATION`` con un permiso
único por acción.
"""

from __future__ import annotations

from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import (
    CASE_VIEW_SCOPE_PERMISSIONS,
    LEAD_VIEW_SCOPE_PERMISSIONS,
    OPPORTUNITY_VIEW_SCOPE_PERMISSIONS,
)
from backend.application.quotes.permissions import QUOTE_VIEW_SCOPE_PERMISSIONS
from backend.domain.crm.exceptions import CRMDomainError

_BY_KEY = {"lead_id": "LEAD", "opportunity_id": "OPPORTUNITY", "case_id": "CASE",
           "quote_id": "QUOTE", "customer_id": "CUSTOMER"}
_SCOPES = {
    "LEAD": LEAD_VIEW_SCOPE_PERMISSIONS,
    "OPPORTUNITY": OPPORTUNITY_VIEW_SCOPE_PERMISSIONS,
    "CASE": CASE_VIEW_SCOPE_PERMISSIONS,
    "QUOTE": QUOTE_VIEW_SCOPE_PERMISSIONS,
}
_NOUN = {"LEAD": "Ese prospecto", "OPPORTUNITY": "Esa oportunidad", "CASE": "Ese caso",
         "QUOTE": "Esa cotización", "CUSTOMER": "Ese cliente"}


def _targets(kwargs: dict) -> list[tuple[str, str]]:
    targets = [(kind, kwargs[key]) for key, kind in _BY_KEY.items() if kwargs.get(key)]
    related_type = str(kwargs.get("related_entity_type") or "")
    if (related_type in _SCOPES or related_type == "CUSTOMER") and kwargs.get(
            "related_entity_id"):
        targets.append((related_type, kwargs["related_entity_id"]))
    return targets


class CRMRecordScopeGuard:
    def __init__(self, connection, resolver: CRMDataScopeResolver,
                 customer_resolver=None) -> None:
        self._conn = connection
        self._resolver = resolver
        #: Auditoría CRM F03: los comandos sobre un cliente (editar, contactos,
        #: crédito…) exigían sólo el permiso; ahora también el alcance de clientes.
        self._customer_resolver = customer_resolver

    def can_see(self, context: CRMScopeContext, kind: str, record_id: str) -> bool:
        """¿El registro está en el alcance del actor? (lecturas de actividades,
        tareas y notas de un registro). Un tipo sin regla o un registro
        inexistente no se bloquea aquí."""
        return self.denial(context, {"related_entity_type": kind,
                                     "related_entity_id": record_id}) is None

    def denial(self, context: CRMScopeContext, kwargs: dict) -> str | None:
        """Motivo para rechazar el comando, o ``None`` si puede ejecutarse.
        Un registro inexistente no se rechaza aquí: el caso de uso responde
        «no existe» con su propio código."""
        for kind, record_id in _targets(kwargs):
            if kind == "CUSTOMER":
                reason = self._customer_denial(context, record_id)
                if reason:
                    return reason
                continue
            record = self._load(kind, record_id)
            if record is None:
                continue
            responsible, creator, branch = record
            try:
                scope = self._resolver.resolve_view_scope(context, _SCOPES[kind])
            except CRMDomainError:
                return f"{_NOUN[kind]} está fuera de tu alcance."
            if not scope.includes(responsible_user_id=responsible, created_by_user_id=creator,
                                  branch_id=branch):
                return (f"{_NOUN[kind]} está fuera de tu alcance: pertenece a otra persona "
                        "o sucursal.")
        return None

    def _customer_denial(self, context: CRMScopeContext, customer_id: str) -> str | None:
        if self._customer_resolver is None:
            return None
        from backend.application.customers.data_scope import CustomerScopeContext
        from backend.application.customers.queries.customer_profile_query_service import (
            CustomerProfileQueryService,
        )
        from backend.domain.customers.exceptions import CustomerDomainError
        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )
        customer = CustomerUnitOfWork(self._conn).customers.get(customer_id)
        if customer is None:
            return None
        branch = context.branch_ids[0] if context.branch_ids else None
        try:
            scope = self._customer_resolver.resolve_view_scope(CustomerScopeContext(
                user_id=context.user_id, branch_id=branch,
                team_member_ids=context.team_member_ids))
        except CustomerDomainError:
            return f"{_NOUN['CUSTOMER']} está fuera de tu alcance."
        if not CustomerProfileQueryService._in_scope(customer, scope):
            return (f"{_NOUN['CUSTOMER']} está fuera de tu alcance: pertenece a otra persona "
                    "o sucursal.")
        return None

    def _load(self, kind: str, record_id: str):
        if kind == "QUOTE":
            from backend.infrastructure.db.repositories.quotes.unit_of_work import (
                QuotesUnitOfWork,
            )
            quote = QuotesUnitOfWork(self._conn).quotes.get(record_id)
            return None if quote is None else (
                quote.created_by_user_id, quote.created_by_user_id, quote.branch_id)
        if kind == "CASE":
            from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
                CustomerServiceUnitOfWork,
            )
            case = CustomerServiceUnitOfWork(self._conn).cases.get(record_id)
            return None if case is None else (
                case.assigned_user_id, case.created_by_user_id, case.origin_branch_id)
        from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
        uow = CRMUnitOfWork(self._conn)
        if kind == "LEAD":
            lead = uow.leads.get(record_id)
            return None if lead is None else (
                lead.assigned_user_id, lead.created_by_user_id, lead.origin_branch_id)
        opportunity = uow.opportunities.get(record_id)
        return None if opportunity is None else (
            opportunity.owner_user_id, opportunity.created_by_user_id,
            opportunity.origin_branch_id)
