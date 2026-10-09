"""Bitácora unificada de Clientes y CRM (§76, CRM-43): las cinco bitácoras del
módulo (clientes, CRM, atención, crédito, privacidad) en una sola lectura.

Sólo lectura; ninguna bitácora se modifica ni se borra (§73: «quien anonimiza
no elimina auditoría»).
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_UNION = """
SELECT 'customers' AS module, created_at, action, actor_user_id, NULL AS authorized_by,
       customer_id, NULL AS entity_type, customer_id AS entity_id, reason, after_json
  FROM customer_audit_log
UNION ALL
SELECT 'crm', created_at, action, actor_user_id, NULL, NULL,
       CASE WHEN lead_id IS NOT NULL THEN 'LEAD'
            WHEN opportunity_id IS NOT NULL THEN 'OPPORTUNITY'
            WHEN activity_id IS NOT NULL THEN 'ACTIVITY'
            WHEN task_id IS NOT NULL THEN 'TASK'
            WHEN note_id IS NOT NULL THEN 'NOTE' END,
       COALESCE(lead_id, opportunity_id, activity_id, task_id, note_id), reason, after_json
  FROM crm_audit_log
UNION ALL
SELECT 'customer_service', created_at, action, actor_user_id, NULL, NULL, 'CASE', case_id,
       reason, after_json
  FROM customer_service_audit_log
UNION ALL
SELECT 'customer_credit', created_at, action, actor_user_id, authorized_by_user_id,
       customer_id, 'CUSTOMER', customer_id, reason, after_json
  FROM customer_credit_audit_log
UNION ALL
SELECT 'customer_privacy', created_at, action, actor_user_id, authorized_by_user_id,
       customer_id, 'CUSTOMER', customer_id, reason, after_json
  FROM customer_privacy_audit_log
"""


class AuditTrailRepository(CustomerRepositoryBase):
    def recent(self, *, limit: int = 500, module: str | None = None,
               action: str | None = None) -> list[dict]:
        where, params = [], []
        if module:
            where.append("module = ?")
            params.append(module)
        if action:
            where.append("action = ?")
            params.append(action)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        return self._query(f"SELECT * FROM ({_UNION}){clause} ORDER BY created_at DESC LIMIT ?",
                           (*params, limit))
