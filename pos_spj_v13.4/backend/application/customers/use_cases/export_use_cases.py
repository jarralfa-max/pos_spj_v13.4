"""Exportaciones de Clientes y CRM (§48, CRM-43).

No existía ninguna: ``ExportCustomersQuery``/``ExportCRMActivitiesQuery``/
``ExportOpportunitiesQuery`` del prompt no tenían código. Reglas:

* permiso por conjunto (``CLIENTES.exportar``, ``CRM.leads.exportar``…);
* alcance: se exporta lo que el usuario puede VER (los mismos servicios de
  consulta con su contexto), nunca la tabla completa;
* sin identificadores internos (folios sí, UUID no);
* datos sensibles (teléfono, correo, RFC) enmascarados salvo que se pidan y se
  tenga ``CLIENTES.sensible.exportar`` (§70) — y entonces con motivo;
* toda exportación deja evidencia en ``customer_audit_log`` (quién, qué
  conjunto, cuántas filas, si incluyó sensibles y por qué) — §73.

Devuelve encabezados y filas; escribir el archivo es de la pantalla.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.value_objects.field_visibility import FieldVisibility, mask
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

EXPORTED = "CUSTOMER_DATA_EXPORTED"

DATASETS = {
    "customers": ("Clientes", CustomerPermissions.EXPORT),
    "leads": ("Prospectos", CRMPermissions.LEADS_EXPORT),
    "opportunities": ("Oportunidades", CustomerPermissions.EXPORT),
    "activities": ("Actividades", CustomerPermissions.EXPORT),
}


@dataclass(frozen=True)
class ExportTable:
    dataset: str
    headers: tuple[str, ...]
    rows: list[tuple] = field(default_factory=list)
    include_sensitive: bool = False


class ExportCustomerDataUseCase:
    """``readers`` son las lecturas YA acotadas por el alcance del usuario
    (las inyecta la raíz de composición): este caso de uso no consulta tablas
    por su cuenta para no saltarse ese alcance."""

    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None, *,
                 readers: dict | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()
        self._readers = readers or {}

    def execute(self, connection, *, actor_user_id: str, dataset: str, operation_id: str,
                include_sensitive: bool = False, reason: str = "") -> CustomerResult:
        if dataset not in DATASETS:
            return CustomerResult.fail("Conjunto de datos no válido.", "VALIDATION",
                                       operation_id=operation_id)
        try:
            self._auth.require(actor_user_id, DATASETS[dataset][1])
            if include_sensitive:
                self._auth.require(actor_user_id, CustomerPermissions.SENSITIVE_DATA_EXPORT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        if include_sensitive and not (reason or "").strip():
            return CustomerResult.fail(
                "Exportar datos sensibles exige indicar el motivo.", "VALIDATION",
                operation_id=operation_id)
        visibility = FieldVisibility.VISIBLE if include_sensitive else FieldVisibility.MASKED
        table = getattr(self, f"_{dataset}")(visibility)
        with CustomerUnitOfWork(connection) as uow:
            uow.audit.record(
                action=EXPORTED, actor_user_id=actor_user_id, customer_id=None,
                after_json=json.dumps({"dataset": dataset, "rows": len(table.rows),
                                       "include_sensitive": bool(include_sensitive)}),
                reason=reason or "exportación", operation_id=operation_id)
        return CustomerResult.ok(
            f"{len(table.rows)} registro(s) de {DATASETS[dataset][0].lower()} listos para "
            "exportar", operation_id=operation_id,
            table=ExportTable(dataset, table.headers, table.rows, bool(include_sensitive)))

    # -- conjuntos -----------------------------------------------------------------
    def _customers(self, visibility: FieldVisibility) -> ExportTable:
        rows = []
        for customer in self._readers["customers"]():
            profile = self._readers["customer_profile_raw"](customer.id)
            primary = next((c for c in profile.contacts if c.is_primary),
                           profile.contacts[0] if profile.contacts else None)
            tax = profile.tax_profile
            rows.append((
                str(customer.code), customer.display_name, customer.legal_name,
                customer.customer_type.value, customer.status.value,
                customer.lifecycle_stage.value, customer.created_at[:10],
                mask(primary.phone_e164 or "", visibility) if primary else "",
                mask(primary.email or "", visibility) if primary else "",
                mask(tax.tax_identifier or "", visibility) if tax else "",
                customer.purchase_count, (customer.last_purchase_at or "")[:10]))
        return ExportTable("customers", (
            "Código", "Nombre", "Razón social", "Tipo", "Estatus", "Etapa", "Alta", "Teléfono",
            "Correo", "RFC", "Compras", "Última compra"), rows)

    def _leads(self, visibility: FieldVisibility) -> ExportTable:
        rows = [(str(lead.code), lead.display_name, lead.company_name, lead.source.value,
                 lead.status.value, lead.priority.value, lead.score,
                 str(lead.estimated_value or ""), mask(lead.phone_e164 or "", visibility),
                 mask(lead.email or "", visibility), lead.created_at[:10])
                for lead in self._readers["leads"]()]
        return ExportTable("leads", ("Folio", "Prospecto", "Empresa", "Fuente", "Estado",
                                     "Prioridad", "Score", "Valor estimado", "Teléfono",
                                     "Correo", "Alta"), rows)

    def _opportunities(self, _visibility: FieldVisibility) -> ExportTable:
        names = self._readers["customer_names"]
        stages = self._readers["stage_names"]()
        items = list(self._readers["opportunities"]())
        customers = names({o.customer_id for o in items})
        rows = [(str(o.code), o.name, customers.get(o.customer_id, ""),
                 stages.get(o.stage_id, ""), o.status.value, str(o.amount or ""),
                 o.probability, str(o.weighted_value),
                 o.expected_close_date.isoformat() if o.expected_close_date else "",
                 o.created_at[:10]) for o in items]
        return ExportTable("opportunities", ("Folio", "Oportunidad", "Cliente", "Etapa",
                                             "Estado", "Valor", "Probabilidad", "Ponderado",
                                             "Cierre esperado", "Alta"), rows)

    def _activities(self, _visibility: FieldVisibility) -> ExportTable:
        rows = [(a.activity_type.value, a.subject, a.related_entity_type.value,
                 a.status.value, (a.scheduled_at or "")[:16], (a.completed_at or "")[:16])
                for a in self._readers["activities"]()]
        return ExportTable("activities", ("Tipo", "Asunto", "Relacionado con", "Estado",
                                          "Programada", "Completada"), rows)
