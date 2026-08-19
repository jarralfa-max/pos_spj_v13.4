"""Shared plumbing for Sales/POS use cases — authorization injection and
outbox event emission. Mirrors
backend/application/customers/use_cases/lifecycle_use_cases.py::_BaseUseCase
(`_emit`) shape, adapted to Sales' outbox repository signature.

Sales' UnitOfWork has no `.audit` repository (SALES-2 deliberately reuses
the generic `core.services.auto_audit.audit_write` sink instead, which needs
a `container`, not a bare `connection` — see backend/application/sales/audit.py's
own docstring). These use cases therefore only enqueue to `sales_outbox`
(real, atomic, backed by SALES-4's schema) — they do NOT call
`record_sales_audit_entry`, since that would require threading a `container`
through every use case in addition to `connection`, a real API-shape
decision deferred to whichever future phase wires these use cases into the
real UI (which already has a `container` on hand). Documented as an open gap
in docs/refactor/SALES-6_application_layer.md, not silently skipped.
"""

from __future__ import annotations

import json

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.domain.sales.events import sale_event_payload


class _SalesBaseUseCase:
    def __init__(self, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or SalesAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = sale_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
