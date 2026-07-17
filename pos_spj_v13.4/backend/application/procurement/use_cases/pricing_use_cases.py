"""Price-variance detection use case (migrated from the legacy audit_write).

Replaces `compras_pro.py`'s inline `audit_write(accion="VARIACION_PRECIO")` with a
canonical, event-driven record: for each captured line it fetches the historical
cost (read service), evaluates the variance (domain PriceVariancePolicy) and, for
significant ones, records an audit row and enqueues a canonical
`PURCHASE_PRICE_VARIANCE_DETECTED` event (post-commit). No float, no widget math.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.queries.purchase_template_read_service import (
    ProductPurchaseCostReadService,
)
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.pricing_policies import PriceVariancePolicy
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


class RecordPurchasePriceVarianceUseCase:
    def __init__(self, *, policy: PriceVariancePolicy | None = None) -> None:
        self._policy = policy or PriceVariancePolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                document_id: str | None, lines: list[dict], branch_id: str | None = None
                ) -> ProcurementResult:
        """lines: [{product_id, captured_cost, historical_cost?}]. When
        historical_cost is absent it is looked up from the read service."""
        costs = ProductPurchaseCostReadService(connection)
        detected: list[dict] = []
        with ProcurementUnitOfWork(connection) as uow:
            for raw in lines:
                product_id = str(raw.get("product_id") or "")
                if not product_id:
                    continue
                historical = raw.get("historical_cost")
                if historical is None:
                    historical = costs.historical_cost(product_id, branch_id=branch_id)
                result = self._policy.evaluate(historical, raw.get("captured_cost"))
                if not result.is_significant:
                    continue
                entry = {
                    "product_id": product_id,
                    "historical_cost": str(result.historical_cost),
                    "captured_cost": str(result.captured_cost),
                    "percent": str(result.percent.quantize(Decimal("0.1"))),
                    "direction": result.direction.value,
                    "label": result.label(),
                }
                detected.append(entry)
                uow.audit.record(
                    action=ProcurementEvents.PURCHASE_PRICE_VARIANCE_DETECTED,
                    actor_user_id=actor_user_id, document_id=document_id,
                    reason=entry["label"],
                    before_json=json.dumps({"unit_cost": entry["historical_cost"]}),
                    after_json=json.dumps({"unit_cost": entry["captured_cost"]}),
                    operation_id=operation_id, branch_id=branch_id)
                payload = build_event_payload(
                    ProcurementEvents.PURCHASE_PRICE_VARIANCE_DETECTED,
                    operation_id=operation_id, document_id=document_id or product_id,
                    user_id=actor_user_id, branch_id=branch_id, **entry)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=ProcurementEvents.PURCHASE_PRICE_VARIANCE_DETECTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        return ProcurementResult.ok("Variaciones evaluadas", operation_id=operation_id,
                                    detected=detected)
