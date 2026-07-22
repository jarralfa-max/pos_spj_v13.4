"""RegisterTraceabilityLinkUseCase (INV-17) — record a genealogy edge (§32-33).

Production and slaughter break a lot's identity: input lots are consumed and a
new output lot is created, and the ledger records those as independent movements.
This use case makes the parent→child relationship explicit so a recall can walk
the genealogy across the identity break. It is idempotent by ``operation_id`` and
emits ``INVENTORY_TRACEABILITY_LINKED`` for downstream consumers.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.traceability_link import TraceabilityLink
from backend.domain.inventory.enums import TraceabilityLinkType
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class RegisterTraceabilityLinkUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, parent_lot_id: str, child_lot_id: str,
                link_type: TraceabilityLinkType, operation_id: str, actor_user_id: str,
                quantity=0, weight=0, product_id: str | None = None,
                source_module: str = "inventory",
                source_document_type: str | None = None,
                source_document_id: str | None = None,
                reason_note: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TRACEABILITY_LINK)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                existing = uow.traceability.find_by_operation_id(operation_id)
                if existing is not None:
                    return InventoryResult.ok(
                        "Enlace de trazabilidad ya registrado (idempotente)",
                        entity_id=existing["id"], operation_id=operation_id,
                        idempotent=True)

                link = TraceabilityLink.create(
                    parent_lot_id=parent_lot_id, child_lot_id=child_lot_id,
                    link_type=link_type, quantity=quantity, weight=weight,
                    product_id=product_id, source_module=source_module,
                    source_document_type=source_document_type,
                    source_document_id=source_document_id, operation_id=operation_id,
                    created_by_user_id=actor_user_id)
                uow.traceability.save(link)

                payload = build_event_payload(
                    InventoryEvents.INVENTORY_TRACEABILITY_LINKED,
                    operation_id=operation_id, entity_id=link.id,
                    product_id=product_id, lot_id=child_lot_id, user_id=actor_user_id,
                    parent_lot_id=parent_lot_id, child_lot_id=child_lot_id,
                    link_type=link_type.value, quantity=str(link.quantity),
                    weight=str(link.weight))
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=InventoryEvents.INVENTORY_TRACEABILITY_LINKED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.audit.record(
                    entity_type="TRACEABILITY_LINK", entity_id=link.id,
                    action=link_type.value, user_id=actor_user_id,
                    operation_id=operation_id, reason=reason_note,
                    product_id=product_id, lot_id=child_lot_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Enlace de trazabilidad registrado",
                                  entity_id=link.id, operation_id=operation_id,
                                  parent_lot_id=parent_lot_id, child_lot_id=child_lot_id)
