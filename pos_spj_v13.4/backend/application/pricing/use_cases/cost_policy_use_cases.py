"""Cambiar la política de costo (GLOBAL / PER_BRANCH), §32.

No recalcula nada: la proyección ya mantiene el costo de empresa y el de cada
sucursal, así que el cambio rige de inmediato. Queda rastro en ``pricing_outbox``
(valor anterior, nuevo y quién lo cambió).
"""

from __future__ import annotations

import json
import logging

from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.pricing.cost_policy import COST_POLICY_LABELS, CostPolicy, CostPolicySettings
from backend.application.pricing.permissions import PricingPermissions
from backend.application.pricing.result import PricingResult
from backend.domain.pricing.events import PricingEvents, build_pricing_event_payload
from backend.domain.pricing.exceptions import PricingPermissionDeniedError
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository

logger = logging.getLogger("spj.pricing.cost_policy")


class SetCostPolicyUseCase:
    def __init__(self, authorization: PricingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PricingAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                policy: str) -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.SETTINGS_MANAGE)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        try:
            new_policy = CostPolicy(str(policy))
        except ValueError:
            return PricingResult.fail("Política de costo no válida", "VALIDATION",
                                      operation_id=operation_id)
        settings = CostPolicySettings(connection)
        previous = settings.current()
        if previous is new_policy:
            return PricingResult.ok("La política de costo ya era ésa", operation_id=operation_id,
                                    policy=new_policy.value, changed=False)
        try:
            settings.store(new_policy)
            payload = build_pricing_event_payload(
                PricingEvents.COST_POLICY_CHANGED, operation_id=operation_id,
                entity_id="costing.cost_policy", user_id=actor_user_id,
                previous=previous.value, policy=new_policy.value)
            PricingRepository(connection).enqueue_event(
                event_id=payload["event_id"], event_name=PricingEvents.COST_POLICY_CHANGED,
                operation_id=operation_id, entity_id="costing.cost_policy",
                payload=json.dumps(payload))
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            logger.exception("No se pudo cambiar la política de costo")
            raise
        return PricingResult.ok(f"Política de costo: {COST_POLICY_LABELS[new_policy]}",
                                operation_id=operation_id, policy=new_policy.value,
                                changed=True)
