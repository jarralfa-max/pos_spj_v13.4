"""Conteos del tablero de CRM (§81, CRM-43). Sólo lectura."""

from __future__ import annotations

from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase


class CRMInsightsRepository(CRMRepositoryBase):
    def active_customers(self) -> int:
        return int(self._scalar("SELECT COUNT(*) FROM customers WHERE status='ACTIVE'",
                                default=0))

    def without_follow_up(self) -> int:
        """Clientes activos sin actividad ni tarea pendiente y sin oportunidad
        abierta: nadie les está dando seguimiento."""
        return int(self._scalar(
            "SELECT COUNT(*) FROM customers c WHERE c.status='ACTIVE'"
            " AND NOT EXISTS (SELECT 1 FROM crm_activities a WHERE a.related_entity_type="
            "'CUSTOMER' AND a.related_entity_id=c.id AND a.status IN ('PLANNED','IN_PROGRESS'))"
            " AND NOT EXISTS (SELECT 1 FROM crm_tasks t WHERE t.related_entity_type='CUSTOMER'"
            " AND t.related_entity_id=c.id AND t.status IN ('PLANNED','IN_PROGRESS'))"
            " AND NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.customer_id=c.id"
            " AND o.status IN ('OPEN','ON_HOLD'))", default=0))

    def customers_by_segment(self) -> list[tuple[str, int]]:
        rows = self._query(
            "SELECT s.name AS name, COUNT(m.id) AS n FROM customer_segments s"
            " LEFT JOIN customer_segment_memberships m ON m.segment_id=s.id"
            " AND m.removed_at IS NULL WHERE s.active=1 GROUP BY s.id ORDER BY n DESC")
        return [(r["name"], int(r["n"])) for r in rows]
