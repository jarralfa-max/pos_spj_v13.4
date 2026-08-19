"""Shared product audit-trail writer (§40).

Before this existed, `product_master_use_cases.py::_audit_code_override` and
`event_handlers/quality_status_handler.py::_audit` each hand-rolled their own
slightly different raw INSERT into `product_audit_log`, and every other
mutation use case (recipe/yield/cutting/bundle versions, imports, branch
assortment, most of the lifecycle transitions) wrote nothing at all — the
audit table existed and was tested in isolation, but only 2 of the module's
~15 real mutation paths ever populated it. `record_product_audit_entry` is the
one place that builds a `ProductAuditEntry` (so its validation actually runs)
and persists it; every use case below calls this instead of its own SQL.
"""

from __future__ import annotations

import json

from backend.domain.products.value_objects.product_audit_entry import ProductAuditEntry


def record_product_audit_entry(
    conn,
    *,
    action: str,
    entity_id: str,
    user_id: str,
    operation_id: str,
    authorized_by: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    branch_id: str | None = None,
    source: str = "products",
) -> None:
    """Build and persist one `ProductAuditEntry` row.

    No-ops if `product_audit_log` doesn't exist yet — mirrors the same
    outbox-table existence guard every use case in this package already uses
    for `product_outbox`, so minimal test fixtures that don't create the full
    schema keep working.
    """
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_audit_log'").fetchone() is None:
        return
    entry = ProductAuditEntry(
        action=action, entity_id=entity_id, user_id=user_id or "system",
        operation_id=operation_id, authorized_by=authorized_by, before=before,
        after=after, reason=reason, branch_id=branch_id, source=source)
    conn.execute(
        "INSERT INTO product_audit_log (id, action, entity_id, user_id, "
        "authorized_by, operation_id, before, after, reason, branch_id, source, "
        "occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry.id, entry.action, entry.entity_id, entry.user_id,
         entry.authorized_by, entry.operation_id,
         json.dumps(entry.before) if entry.before is not None else None,
         json.dumps(entry.after) if entry.after is not None else None,
         entry.reason, entry.branch_id, entry.source, entry.occurred_at))
