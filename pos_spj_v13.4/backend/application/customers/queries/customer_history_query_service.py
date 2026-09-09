"""CustomerHistoryQueryService (§29, §57) — the canonical
CustomerActivityTimeline: one chronological feed of everything that
happened to a customer, merged from every bounded context's own audit
log. Reads only; never mutates.

This is the one place in the CRM-0..12 pipeline that deliberately reads
raw SQL from OTHER bounded contexts' tables — a documented exception to
the "never reach into another bounded context's tables" rule CRM-8/9/11
held for *writes*. Reading for display aggregation is a different concern
than writing: nothing here would leave those tables in a state their own
use cases didn't already put them in, and precedent already exists
(``CustomerAccountsReceivableSummaryQuery`` has read Finanzas' own
``cuentas_por_cobrar`` table read-only since CRM-8). Building a
Customer 360/timeline view is *specifically what this pattern is for*.

Correlation to customer_id per source:
  - customers: ``customer_audit_log.customer_id`` — direct.
  - crm: ``crm_audit_log`` has no customer_id column (it's keyed by lead/
    opportunity/activity/task/note id) — correlated via
    ``opportunities.customer_id`` only. Leads are deliberately NOT
    included: a Lead has no customer_id until it converts, and the
    resulting Opportunity's own trail carries the relationship forward
    from there.
  - customer_service: ``customer_service_audit_log`` has no customer_id
    column either — correlated via ``service_cases.customer_id``.
  - customer_credit / customer_privacy: their own audit tables already
    carry ``customer_id`` directly.
  - ventas (CRM-33): Ventas has no ``customer_id`` column at all —
    ``ventas.cliente_id`` is the legacy identity, never migrated (same
    documented gap as ``CustomerAccountsReceivableSummaryQuery``).
    Correlated via ``customers.legacy_customer_id`` (CRM-21's bridge):
    resolve ``customer_id`` → legacy id first, then read ``ventas`` by
    that legacy id. A customer with no bridge row (native Customer Master
    creation, never mirrored from a legacy ``clientes`` row) simply
    contributes no sales entries — not an error, same "missing means
    nothing to contribute" discipline as ``_table_exists``.
  - crm activities/tasks/notes (CRM-38, Fase 4): unlike leads/
    opportunities, these three ARE directly correlatable —
    ``CRMRelatedEntityType.CUSTOMER`` exists precisely so an
    Activity/Task/Note can point at a customer without going through an
    Opportunity first. Correlated the same way as ``_crm_entries``, just
    a different ``related_entity_type`` filter, then joined to
    ``crm_audit_log`` via ``activity_id``/``task_id``/``note_id``.
  - pedidos_whatsapp (CRM-38, Fase 4): same legacy-bridge pattern as
    ventas — ``pedidos_whatsapp.cliente_id`` is the legacy id, resolved
    the same way.

Gated by ``AUDIT_VIEW`` (§76) — viewing a customer's full cross-context
history is an audit concern, not a profile-viewing concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.exceptions import CustomerDomainError


@dataclass(frozen=True)
class CustomerTimelineEntry:
    occurred_at: str
    source_module: str
    action: str
    actor_user_id: str | None
    reason: str
    source_entity_id: str | None


class CustomerHistoryQueryService:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_timeline(self, customer_id: str, *, actor_user_id: str,
                     limit: int = 200) -> list[CustomerTimelineEntry]:
        self._auth.require(actor_user_id, CustomerPermissions.AUDIT_VIEW)
        entries: list[CustomerTimelineEntry] = []
        entries.extend(self._customers_entries(customer_id))
        entries.extend(self._crm_entries(customer_id))
        entries.extend(self._service_entries(customer_id))
        entries.extend(self._credit_entries(customer_id))
        entries.extend(self._privacy_entries(customer_id))
        entries.extend(self._sales_entries(customer_id))
        entries.extend(self._crm_direct_entries(customer_id))
        entries.extend(self._whatsapp_order_entries(customer_id))
        entries.sort(key=lambda e: e.occurred_at, reverse=True)
        return entries[:limit]

    def _customers_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at FROM customer_audit_log"
            " WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customers", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=customer_id) for r in rows]

    def _crm_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("crm_audit_log") and self._table_exists("opportunities")):
            return []
        rows = self._conn.execute(
            "SELECT a.action, a.actor_user_id, a.reason, a.created_at, a.opportunity_id"
            " FROM crm_audit_log a"
            " WHERE a.opportunity_id IN (SELECT id FROM opportunities WHERE customer_id=?)",
            (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="crm", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _service_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("customer_service_audit_log")
                and self._table_exists("service_cases")):
            return []
        rows = self._conn.execute(
            "SELECT a.action, a.actor_user_id, a.reason, a.created_at, a.case_id"
            " FROM customer_service_audit_log a"
            " WHERE a.case_id IN (SELECT id FROM service_cases WHERE customer_id=?)",
            (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_service", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _credit_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_credit_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at, profile_id"
            " FROM customer_credit_audit_log WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_credit", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _privacy_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_privacy_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at, request_id"
            " FROM customer_privacy_audit_log WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_privacy", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _sales_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        """Lee `v_ventas_unificada`, no `ventas` (migración 256).

        Leer la tabla legacy dejaba fuera del historial del cliente TODAS las
        ventas del POS: desde SALES-19..22 nacen en el agregado canónico
        (`sales`) y nunca pasan por `ventas`. La vista es la única fuente que
        contiene ambas, y las seis columnas que este método usa mapean sin
        pérdida (a diferencia de, p. ej., `loyalty_points`, que no tiene
        equivalente canónico y por eso su lector sigue sin repuntarse).

        Se conserva el respaldo a `ventas` para una BD que aún no haya
        aplicado la 256; desaparece con la vista.
        """
        source = ("v_ventas_unificada" if self._relation_exists("v_ventas_unificada")
                  else "ventas")
        if not (self._relation_exists(source) and self._table_exists("customers")):
            return []
        legacy_customer_id = self._legacy_customer_id(customer_id)
        if not legacy_customer_id:
            return []
        rows = self._conn.execute(
            f"SELECT id, folio, total, estado, usuario, fecha FROM {source}"
            " WHERE cliente_id=?",
            (legacy_customer_id,)).fetchall()
        action_by_estado = {
            "cancelada": "VENTA_CANCELADA", "cancelado": "VENTA_CANCELADA",
        }
        entries = []
        for sale_id, folio, total, estado, usuario, fecha in rows:
            action = action_by_estado.get(str(estado or "").lower(), "VENTA_COMPLETADA")
            monto = f"${float(total or 0):,.2f}"
            entries.append(CustomerTimelineEntry(
                occurred_at=fecha, source_module="ventas", action=action,
                actor_user_id=usuario, reason=f"Folio {folio or sale_id} · {monto}",
                source_entity_id=sale_id))
        return entries

    def _crm_direct_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("crm_audit_log") and self._table_exists("crm_activities")
                and self._table_exists("crm_tasks") and self._table_exists("crm_notes")):
            return []
        rows = self._conn.execute(
            "SELECT a.action, a.actor_user_id, a.reason, a.created_at,"
            " COALESCE(a.activity_id, a.task_id, a.note_id) AS entity_id"
            " FROM crm_audit_log a"
            " WHERE a.activity_id IN"
            "   (SELECT id FROM crm_activities WHERE related_entity_type='CUSTOMER'"
            "     AND related_entity_id=?)"
            "    OR a.task_id IN"
            "   (SELECT id FROM crm_tasks WHERE related_entity_type='CUSTOMER'"
            "     AND related_entity_id=?)"
            "    OR a.note_id IN"
            "   (SELECT id FROM crm_notes WHERE related_entity_type='CUSTOMER'"
            "     AND related_entity_id=?)",
            (customer_id, customer_id, customer_id)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="crm", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _whatsapp_order_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("pedidos_whatsapp") and self._table_exists("customers")):
            return []
        legacy_customer_id = self._legacy_customer_id(customer_id)
        if not legacy_customer_id:
            return []
        rows = self._conn.execute(
            "SELECT id, estado, total, fecha FROM pedidos_whatsapp WHERE cliente_id=?",
            (legacy_customer_id,)).fetchall()
        entries = []
        for pedido_id, estado, total, fecha in rows:
            monto = f"${float(total or 0):,.2f}"
            entries.append(CustomerTimelineEntry(
                occurred_at=fecha, source_module="whatsapp", action="PEDIDO_WHATSAPP",
                actor_user_id=None, reason=f"Estado {estado or '—'} · {monto}",
                source_entity_id=pedido_id))
        return entries

    def _legacy_customer_id(self, customer_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT legacy_customer_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        return row[0] if row else None

    def _table_exists(self, name: str) -> bool:
        """Sibling bounded contexts are optional at the schema level (a
        deployment could run migrations up to a point before CRM-8/9/10
        landed, or a test fixture may only load one schema) — a missing
        table means "nothing to contribute", not an error."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def _relation_exists(self, name: str) -> bool:
        """Como `_table_exists`, pero también acepta vistas.

        Separado a propósito en vez de ensanchar `_table_exists`: sus otras
        ocho llamadas comprueban tablas reales, y `type='table'` filtraría la
        vista `v_ventas_unificada` haciendo que el repunte de lectura fuera un
        no-op silencioso (se cayó en ello al escribirlo).
        """
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone() is not None
