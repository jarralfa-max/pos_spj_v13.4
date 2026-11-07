"""Driver settlement use cases (master prompt §46). `CreateDriverSettlementUseCase`
gathers every collected `DriverCashCollection` for the driver, reconciles them
into one `DriverSettlement`, and marks each included collection `SETTLED` in the
same transaction — a collection is never left "pending settlement" while already
claimed by a settlement. Nothing else moves a collection to `PENDING_SETTLEMENT`,
so a just-collected one has to be picked up here too (SDLC-ORD-001): otherwise no
driver could ever be settled.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.audit import OrdersDeliveryAuditActions
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.enums import (
    CollectionPaymentMethod,
    CollectionStatus,
    SettlementStatus,
)
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import (
    OrdersDeliveryDomainError,
    SettlementNotFoundError,
)
from backend.domain.orders_delivery.settlement import DriverSettlement
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.shared.ids import new_uuid


class CreateDriverSettlementUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, driver_id: str, branch_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTLEMENT_CREATE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            pending = [
                collection
                for status in (CollectionStatus.PENDING_SETTLEMENT, CollectionStatus.COLLECTED,
                               CollectionStatus.PARTIALLY_COLLECTED)
                for collection in uow.cash_collections.list_for_driver(driver_id, status=status)]
            try:
                settlement = DriverSettlement.create(
                    driver_id=driver_id, branch_id=branch_id, collections=pending)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            for collection in pending:
                if collection.status != CollectionStatus.PENDING_SETTLEMENT:
                    collection.mark_pending_settlement()
                collection.mark_settled()
                uow.cash_collections.save(collection)
            uow.settlements.save(settlement)
            self._emit_delivery(
                uow, DeliveryEvents.DRIVER_SETTLEMENT_CREATED, entity_id=settlement.id,
                operation_id=operation_id, branch_id=branch_id, actor_user_id=actor_user_id,
                driver_id=driver_id)
            if settlement.status == SettlementStatus.WITH_DIFFERENCE:
                # §57's UNIQUE(operation_id) is one outbox row per real
                # operation, and `delivery_event_payload()` requires a
                # genuine UUIDv7 — a string suffix like f"{operation_id}-x"
                # fails that validation (unlike ORD-8's per-line reservation
                # ids, which cross into Inventory's own, more lenient
                # operation_id column). This second event is a distinct
                # notification triggered by the same call, not the same
                # idempotent operation, so it earns its own fresh id.
                self._emit_delivery(
                    uow, DeliveryEvents.DRIVER_SETTLEMENT_DIFFERENCE_DETECTED,
                    entity_id=settlement.id, operation_id=new_uuid(),
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    difference=str(settlement.difference))
        return OrderResult.ok(
            "Liquidación creada", entity_id=settlement.id, operation_id=operation_id,
            status=settlement.status.value, difference=settlement.difference)


class ApproveDriverSettlementUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, settlement_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTLEMENT_APPROVE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            settlement = uow.settlements.get(settlement_id)
            if settlement is None:
                return fail_from_domain_error(
                    SettlementNotFoundError(f"Liquidación {settlement_id} no existe"),
                    operation_id=operation_id)
            try:
                if settlement.status == SettlementStatus.WITH_DIFFERENCE:
                    settlement.submit_for_review(reviewed_by_user_id=actor_user_id)
                else:
                    settlement.approve(approved_by_user_id=actor_user_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.settlements.save(settlement)
            self._audit(
                uow, (OrdersDeliveryAuditActions.DRIVER_SETTLEMENT_SUBMITTED_FOR_REVIEW
                      if settlement.status == SettlementStatus.PENDING_REVIEW
                      else OrdersDeliveryAuditActions.DRIVER_SETTLEMENT_APPROVED), entity="DriverSettlement", entity_id=settlement.id,
                branch_id=settlement.branch_id, actor_user_id=actor_user_id, operation_id=operation_id,
                status=settlement.status.value)
        return OrderResult.ok(
            "Liquidación procesada", entity_id=settlement.id, operation_id=operation_id,
            status=settlement.status.value)


class CloseDriverSettlementUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, settlement_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTLEMENT_CLOSE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            settlement = uow.settlements.get(settlement_id)
            if settlement is None:
                return fail_from_domain_error(
                    SettlementNotFoundError(f"Liquidación {settlement_id} no existe"),
                    operation_id=operation_id)
            try:
                if settlement.status == SettlementStatus.APPROVED:
                    settlement.post()
                settlement.close()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.settlements.save(settlement)
            # Finanzas sólo mueve el EFECTIVO: lo cobrado con tarjeta o
            # transferencia nunca quedó en manos del repartidor.
            efectivo = [
                cobro for cobro in map(uow.cash_collections.get, settlement.collection_ids)
                if cobro is not None and cobro.payment_method == CollectionPaymentMethod.CASH]
            self._emit_delivery(
                uow, DeliveryEvents.DRIVER_SETTLEMENT_CLOSED, entity_id=settlement.id,
                operation_id=operation_id, branch_id=settlement.branch_id,
                actor_user_id=actor_user_id, driver_id=settlement.driver_id,
                cash_expected=str(sum((c.expected_amount for c in efectivo), Decimal("0"))),
                cash_collected=str(sum((c.collected_amount for c in efectivo), Decimal("0"))))
        return OrderResult.ok(
            "Liquidación cerrada", entity_id=settlement.id, operation_id=operation_id)
