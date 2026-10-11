"""AutomationSweepRepository (CRM-43) — las consultas de los disparadores por
tiempo de §56.

Cada método devuelve pares ``(id del registro, ancla)``. El ancla es el momento
desde el que cuenta la condición (último movimiento, última compra, última
revisión…): una regla se dispara una sola vez por registro y ancla, y vuelve a
poder dispararse sólo cuando el registro se mueve y vuelve a cruzar el umbral.

Las fechas se comparan como texto ISO-8601 en UTC, igual que en el resto del CRM.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

#: Último movimiento de un prospecto/oportunidad: su propia edición, el último
#: contacto o la última actividad registrada sobre él.
_LAST_TOUCH = (
    "MAX(COALESCE(t.updated_at, t.created_at), COALESCE({extra}, ''),"
    " COALESCE((SELECT MAX(COALESCE(a.completed_at, a.updated_at)) FROM crm_activities a"
    "           WHERE a.related_entity_type='{kind}' AND a.related_entity_id=t.id), ''))"
)


class AutomationSweepRepository(CRMRepositoryBase):
    def idle_leads(self, cutoff: str, *, limit: int) -> list[tuple[str, str]]:
        touch = _LAST_TOUCH.format(extra="t.last_contact_at", kind="LEAD")
        return self._pairs(
            f"SELECT t.id, {touch} AS anchor FROM leads t"
            " WHERE t.status NOT IN ('CONVERTED','ARCHIVED','LOST','UNQUALIFIED')"
            f" AND {touch} < ? ORDER BY anchor LIMIT ?", (cutoff, limit))

    def idle_opportunities(self, cutoff: str, *, limit: int) -> list[tuple[str, str]]:
        touch = _LAST_TOUCH.format(extra="NULL", kind="OPPORTUNITY")
        return self._pairs(
            f"SELECT t.id, {touch} AS anchor FROM opportunities t WHERE t.status='OPEN'"
            f" AND {touch} < ? ORDER BY anchor LIMIT ?", (cutoff, limit))

    def overdue_opportunities(self, today: str, *, limit: int) -> list[tuple[str, str]]:
        """Abiertas con fecha estimada de cierre ya pasada. El ancla es la propia
        fecha de cierre: si la mueven, la regla puede volver a avisar."""
        return self._pairs(
            "SELECT id, expected_close_date FROM opportunities WHERE status='OPEN'"
            " AND expected_close_date IS NOT NULL AND expected_close_date <> ''"
            " AND expected_close_date < ? ORDER BY expected_close_date LIMIT ?", (today, limit))

    def inactive_customers(self, cutoff: str, *, limit: int) -> list[tuple[str, str]]:
        """Clientes activos que ya compraron y llevan el umbral sin comprar. Los que
        nunca han comprado no son «inactivos»: no hay relación que reactivar."""
        return self._pairs(
            "SELECT id, last_purchase_at FROM customers WHERE status='ACTIVE'"
            " AND last_purchase_at IS NOT NULL AND last_purchase_at <> ''"
            " AND last_purchase_at < ? ORDER BY last_purchase_at LIMIT ?", (cutoff, limit))

    def credit_reviews_due(self, cutoff: str, *, limit: int) -> list[tuple[str, str]]:
        """Crédito autorizado cuya última revisión (o autorización) es anterior al umbral."""
        return self._pairs(
            "SELECT customer_id, COALESCE(review_at, authorized_at, updated_at) AS anchor"
            " FROM customer_credit_profiles WHERE status='AUTHORIZED'"
            " AND COALESCE(review_at, authorized_at, updated_at) < ?"
            " ORDER BY anchor LIMIT ?", (cutoff, limit))

    def last_execution_at(self, rule_id: str, target_entity_type: str,
                          target_entity_id: str) -> str | None:
        return self._scalar(
            "SELECT MAX(executed_at) FROM crm_automation_executions"
            " WHERE rule_id=? AND target_entity_type=? AND target_entity_id=?",
            (rule_id, target_entity_type, target_entity_id))

    def responsible_of(self, target_entity_type: str, target_entity_id: str) -> tuple[str | None, str | None]:
        """(responsable, sucursal) del registro — a quién avisar «al responsable»."""
        sql = {
            "LEAD": "SELECT assigned_user_id, origin_branch_id FROM leads WHERE id=?",
            "OPPORTUNITY": "SELECT owner_user_id, origin_branch_id FROM opportunities WHERE id=?",
            "CASE": "SELECT assigned_user_id, origin_branch_id FROM service_cases WHERE id=?",
            "CUSTOMER": "SELECT account_owner_user_id, origin_branch_id FROM customers WHERE id=?",
        }.get(target_entity_type)
        if sql is None:
            return None, None
        row = self._query_one(sql, (target_entity_id,))
        if row is None:
            return None, None
        values = list(row.values())
        return values[0] or None, values[1] or None

    def describe(self, target_entity_type: str, target_entity_id: str) -> str:
        """Nombre legible del registro para el texto del aviso."""
        sql = {
            "LEAD": "SELECT display_name FROM leads WHERE id=?",
            "OPPORTUNITY": "SELECT name FROM opportunities WHERE id=?",
            "CASE": "SELECT case_number || ' · ' || subject FROM service_cases WHERE id=?",
            "CUSTOMER": "SELECT display_name FROM customers WHERE id=?",
        }.get(target_entity_type)
        return (self._scalar(sql, (target_entity_id,), default="") if sql else "") or ""

    def _pairs(self, sql: str, params: tuple) -> list[tuple[str, str]]:
        return [(row[0], row[1] or "") for row in self._conn.execute(sql, params).fetchall()]
