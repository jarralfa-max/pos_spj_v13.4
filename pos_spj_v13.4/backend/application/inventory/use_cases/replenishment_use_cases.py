"""Replenishment use cases (§34, INV-18).

- ``SetReplenishmentRuleUseCase``: define/update the min/max/safety/target policy
  for a product at a branch/warehouse (permission REPLENISHMENT_MANAGE).
- ``GenerateReplenishmentSuggestionsUseCase``: evaluate active rules against
  current availability and emit suggestions (purchase vs transfer). Planning
  only — it never moves stock; a suggestion is acted on through the procurement
  or transfer use cases. Idempotent by the run's ``operation_id`` (permission
  REPLENISHMENT_GENERATE).
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.replenishment import (
    ReplenishmentRule,
    ReplenishmentSuggestion,
)
from backend.domain.inventory.enums import (
    ReplenishmentBasis,
    ReplenishmentSource,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.services.replenishment_policy import ReplenishmentPolicy
from backend.infrastructure.db.repositories.inventory.replenishment_repository import (
    rule_from_row,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class SetReplenishmentRuleUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, product_id: str, branch_id: str,
                warehouse_id: str, reorder_point, target_quantity,
                actor_user_id: str, basis: ReplenishmentBasis = ReplenishmentBasis.QUANTITY,
                min_quantity=0, max_quantity=None, safety_stock=0, lead_time_days: int = 0,
                preferred_source: ReplenishmentSource = ReplenishmentSource.PURCHASE,
                source_warehouse_id: str | None = None,
                active: bool = True) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.REPLENISHMENT_MANAGE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        try:
            rule = ReplenishmentRule.create(
                product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                reorder_point=reorder_point, target_quantity=target_quantity, basis=basis,
                min_quantity=min_quantity, max_quantity=max_quantity,
                safety_stock=safety_stock, lead_time_days=lead_time_days,
                preferred_source=preferred_source,
                source_warehouse_id=source_warehouse_id, active=active)
            with InventoryUnitOfWork(connection) as uow:
                existing = uow.replenishment_rules.get(
                    product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id)
                if existing is not None:
                    rule.id = existing["id"]
                    rule.created_at = existing["created_at"]
                uow.replenishment_rules.upsert(rule)
                uow.audit.record(
                    entity_type="REPLENISHMENT_RULE", entity_id=rule.id,
                    action="UPSERT", user_id=actor_user_id, product_id=product_id,
                    branch_id=branch_id, warehouse_id=warehouse_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION")
        return InventoryResult.ok("Regla de reposición guardada", entity_id=rule.id)


class GenerateReplenishmentSuggestionsUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None,
                 policy: ReplenishmentPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._policy = policy or ReplenishmentPolicy()

    def execute(self, connection, *, operation_id: str, actor_user_id: str,
                branch_id: str | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id,
                               InventoryPermissions.REPLENISHMENT_GENERATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)

        availability = InventoryAvailabilityQueryService(connection)
        suggestions: list[ReplenishmentSuggestion] = []
        with InventoryUnitOfWork(connection) as uow:
            if uow.replenishment_suggestions.exists_for_operation(operation_id):
                return InventoryResult.ok(
                    "Sugerencias ya generadas (idempotente)", operation_id=operation_id,
                    idempotent=True, count=0)

            for row in uow.replenishment_rules.list_active(branch_id=branch_id):
                rule = rule_from_row(row)
                available = availability.get_availability(
                    product_id=rule.product_id, branch_id=rule.branch_id,
                    warehouse_id=rule.warehouse_id).available
                source_surplus = None
                if (rule.preferred_source is ReplenishmentSource.TRANSFER
                        and rule.source_warehouse_id):
                    source_surplus = availability.available_at_warehouse(
                        product_id=rule.product_id,
                        warehouse_id=rule.source_warehouse_id)
                decision = self._policy.evaluate(
                    rule, available=available, source_surplus=source_surplus)
                if decision is None:
                    continue
                suggestion = ReplenishmentSuggestion.create(
                    rule_id=rule.id, product_id=rule.product_id, branch_id=rule.branch_id,
                    warehouse_id=rule.warehouse_id, basis=rule.basis,
                    current_available=available,
                    suggested_quantity=decision.suggested_quantity,
                    source_type=decision.source_type, urgency=decision.urgency,
                    source_warehouse_id=decision.source_warehouse_id,
                    operation_id=operation_id)
                uow.replenishment_suggestions.save(suggestion)
                suggestions.append(suggestion)

                payload = build_event_payload(
                    InventoryEvents.INVENTORY_REPLENISHMENT_SUGGESTED,
                    operation_id=operation_id, entity_id=suggestion.id,
                    product_id=rule.product_id, branch_id=rule.branch_id,
                    warehouse_id=rule.warehouse_id, user_id=actor_user_id,
                    source_type=decision.source_type.value, urgency=decision.urgency.value,
                    suggested_quantity=str(decision.suggested_quantity),
                    source_warehouse_id=decision.source_warehouse_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=InventoryEvents.INVENTORY_REPLENISHMENT_SUGGESTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)

        return InventoryResult.ok(
            f"{len(suggestions)} sugerencia(s) de reposición generada(s)",
            operation_id=operation_id, count=len(suggestions),
            suggestion_ids=[s.id for s in suggestions])
