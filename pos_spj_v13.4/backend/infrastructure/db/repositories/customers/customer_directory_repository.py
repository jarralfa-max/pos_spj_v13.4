"""Datos del directorio de clientes (§83, CRM-43) en lote: contacto
principal, responsable vigente, segmentos, estatus de crédito y última
actividad — sin una consulta por renglón."""

from __future__ import annotations

from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase


class CustomerDirectoryRepository(CustomerRepositoryBase):
    def _has(self, table: str) -> bool:
        return bool(self._query("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?",
                                (table,)))

    def enrich(self, customer_ids: tuple[str, ...]) -> dict[str, dict]:
        ids = tuple(dict.fromkeys(i for i in customer_ids if i))
        result: dict[str, dict] = {i: {"segments": []} for i in ids}
        if not ids:
            return result
        marks = ",".join("?" for _ in ids)
        for r in self._query(
                "SELECT customer_id, phone_e164, email, first_name, last_name"
                f" FROM customer_contacts WHERE customer_id IN ({marks}) AND status='ACTIVE'"
                " ORDER BY is_primary DESC", ids):
            result[r["customer_id"]].setdefault("contact", r)
        if self._has("customer_ownerships"):
            for r in self._query(
                    "SELECT customer_id, owner_user_id FROM customer_ownerships"
                    f" WHERE customer_id IN ({marks}) AND ownership_type='PRIMARY'"
                    " ORDER BY created_at DESC, id DESC", ids):
                result[r["customer_id"]].setdefault("owner_user_id", r["owner_user_id"])
        if self._has("customer_segment_memberships"):
            for r in self._query(
                    "SELECT m.customer_id, s.name FROM customer_segment_memberships m"
                    " JOIN customer_segments s ON s.id=m.segment_id"
                    f" WHERE m.customer_id IN ({marks}) AND m.removed_at IS NULL", ids):
                result[r["customer_id"]]["segments"].append(r["name"])
        if self._has("customer_credit_profiles"):
            for r in self._query(
                    "SELECT customer_id, status FROM customer_credit_profiles"
                    f" WHERE customer_id IN ({marks})", ids):
                result[r["customer_id"]]["credit_status"] = r["status"]
        if self._has("crm_activities"):
            for r in self._query(
                    "SELECT related_entity_id AS cid, MAX(COALESCE(completed_at, scheduled_at))"
                    " AS last FROM crm_activities WHERE related_entity_type='CUSTOMER'"
                    f" AND related_entity_id IN ({marks}) GROUP BY related_entity_id", ids):
                result[r["cid"]]["last_activity_at"] = r["last"]
        return result
