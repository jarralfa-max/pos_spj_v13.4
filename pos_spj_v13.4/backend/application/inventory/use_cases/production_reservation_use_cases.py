"""Reserva de existencia para una orden de producción (Inventario decide lotes).

POR QUÉ UN CASO DE USO PROPIO
-----------------------------
`CreateReservationUseCase` retiene UN saldo concreto (producto, almacén,
ubicación, lote) y `AllocateReservationUseCase` reparte después entre lotes sin
llevar la ubicación: para un insumo controlado por lote, lo reservado y lo
asignado podían quedar en filas de saldo distintas. Aquí Inventario elige
primero qué saldos cubren la demanda (FEFO, FIFO o el orden manual autorizado)
y reserva cada saldo EXACTO — lote y ubicación incluidos — en una sola
transacción.

La estrategia (FEFO, FIFO, LIFO o manual autorizada) es de Inventario: si quien
reserva no la indica, se lee de `inventory_settings` con la clave
`production.allocation_strategy`, del almacén a la sucursal y a lo global; sin
configurar, FEFO.

Todo o nada: si lo elegible no alcanza, no se reserva nada y se devuelve cuánto
hay disponible. Procesamiento deja entonces la orden en MATERIALS_PENDING; no
retiene la mitad ni inventa existencia.

Idempotente por documento origen: reintentar con el mismo
`source_document_id` devuelve las reservas ya creadas en vez de duplicarlas.
Cada reserva tiene su propia identidad y su propio `operation_id` (UUIDv7).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.use_cases.reservation_use_cases import _emit, _scope_fail
from backend.domain.inventory.entities.reservation import InventoryReservation
from backend.domain.inventory.enums import (
    AllocationStrategy,
    InventoryStatus,
    LotQualityStatus,
    ReservationSource,
    ReservationStatus,
)
from backend.domain.inventory.events import InventoryEvents
from backend.domain.inventory.exceptions import (
    InsufficientInventoryError,
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.services.lot_allocation_service import (
    LotAllocationService,
    LotCandidate,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.shared.ids import new_uuid


def _dec(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


STRATEGY_SETTING = "production.allocation_strategy"
DEFAULT_STRATEGY = AllocationStrategy.FEFO


def configured_strategy(uow, *, branch_id: str, warehouse_id: str) -> AllocationStrategy:
    """Estrategia de asignación configurada, de lo particular a lo general."""
    for scope_type, scope_id in (("WAREHOUSE", warehouse_id), ("BRANCH", branch_id),
                                 ("GLOBAL", "")):
        valor = uow.settings.get(setting_key=STRATEGY_SETTING, scope_type=scope_type,
                                 scope_id=scope_id or "")
        if valor:
            return AllocationStrategy(valor)
    return DEFAULT_STRATEGY


@dataclass(frozen=True)
class ProductionReservationLine:
    reservation_id: str
    lot_id: str | None
    location_id: str | None
    quantity: Decimal


class ReserveStockForProductionUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        if authorization is None:
            raise ValueError("ReserveStockForProductionUseCase requiere una política de "
                             "autorización explícita")
        self._auth = authorization
        self._allocator = LotAllocationService()

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                quantity, source_document_id: str, operation_id: str, actor_user_id: str,
                lot_required: bool, strategy: AllocationStrategy | None = None,
                preferred_lot_ids: tuple[str, ...] = (),
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        denied = _scope_fail(context, branch_id, warehouse_id, operation_id)
        if denied is not None:
            return denied
        pedido = _dec(quantity)
        if pedido <= 0:
            return InventoryResult.fail("La cantidad a reservar debe ser positiva",
                                        "INVALID_QUANTITY", operation_id=operation_id)
        if strategy is None:
            try:
                strategy = configured_strategy(InventoryUnitOfWork(connection),
                                               branch_id=branch_id, warehouse_id=warehouse_id)
            except ValueError as exc:
                return InventoryResult.fail(
                    f"Estrategia de asignación mal configurada: {exc}",
                    "ALLOCATION_STRATEGY_INVALID", operation_id=operation_id)
        strategy = AllocationStrategy(strategy)
        if strategy is AllocationStrategy.MANUAL_AUTHORIZED and not preferred_lot_ids:
            return InventoryResult.fail(
                "La asignación manual necesita los lotes elegidos", "MANUAL_LOTS_REQUIRED",
                operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                previas = [r for r in uow.reservations.list_active_for_source_document(
                    source_document_id) if r.source is ReservationSource.PRODUCTION_ORDER
                    and r.product_id == product_id]
                if previas:
                    return InventoryResult.ok(
                        "Existencia ya reservada para este requerimiento (idempotente)",
                        entity_id=source_document_id, operation_id=operation_id,
                        already_processed=True, lines=[
                            ProductionReservationLine(r.id, r.lot_id, r.location_id,
                                                      r.quantity) for r in previas])
                candidatos = self._candidates(uow, product_id=product_id, branch_id=branch_id,
                                              warehouse_id=warehouse_id,
                                              lot_required=lot_required)
                if strategy is AllocationStrategy.MANUAL_AUTHORIZED:
                    orden = {lot: i for i, lot in enumerate(preferred_lot_ids)}
                    candidatos = sorted(
                        (c for c in candidatos if c.lot_id in orden),
                        key=lambda c: orden[c.lot_id])
                disponible = sum((c.available_quantity for c in self._allocator.eligible(
                    candidatos, require_released=True)), Decimal("0"))
                try:
                    plan = self._allocator.allocate(candidatos, pedido, strategy=strategy,
                                                    require_released=True)
                except InsufficientInventoryError:
                    return InventoryResult.fail(
                        f"Existencia elegible insuficiente: se piden {pedido}, "
                        f"hay {disponible}", "INSUFFICIENT_AVAILABILITY",
                        operation_id=operation_id, available=disponible, requested=pedido)
                lineas: list[ProductionReservationLine] = []
                for rebanada in plan:
                    saldo = uow.balances.get(
                        product_id=product_id, branch_id=branch_id,
                        warehouse_id=warehouse_id, inventory_status=InventoryStatus.AVAILABLE,
                        location_id=rebanada.location_id, lot_id=rebanada.lot_id)
                    if saldo is None:
                        raise InventoryDomainError("El saldo elegido desapareció al reservar")
                    saldo.reserve(quantity=rebanada.quantity, weight=Decimal("0"))
                    uow.balances.upsert(saldo)
                    reserva = InventoryReservation.create(
                        product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                        source=ReservationSource.PRODUCTION_ORDER,
                        source_document_id=source_document_id, operation_id=new_uuid(),
                        quantity=rebanada.quantity, weight=0,
                        status=ReservationStatus.CONFIRMED, location_id=rebanada.location_id,
                        lot_id=rebanada.lot_id, created_by_user_id=actor_user_id)
                    uow.reservations.save(reserva)
                    uow.audit.record(
                        entity_type="RESERVATION", entity_id=reserva.id, action="RESERVED",
                        user_id=actor_user_id, operation_id=reserva.operation_id,
                        product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                        location_id=rebanada.location_id, lot_id=rebanada.lot_id,
                        reason=f"producción · {strategy.value}")
                    _emit(uow, InventoryEvents.INVENTORY_RESERVED,
                          operation_id=reserva.operation_id, entity_id=reserva.id,
                          product_id=product_id, branch_id=branch_id,
                          warehouse_id=warehouse_id, actor_user_id=actor_user_id,
                          source_document_id=source_document_id,
                          correlation_id=operation_id)
                    lineas.append(ProductionReservationLine(
                        reserva.id, rebanada.lot_id, rebanada.location_id, rebanada.quantity))
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Existencia reservada para producción",
                                  entity_id=source_document_id, operation_id=operation_id,
                                  lines=lineas)

    @staticmethod
    def _candidates(uow, *, product_id, branch_id, warehouse_id, lot_required):
        lotes = {row["id"]: row for row in uow.lots.list_for_product(product_id)}
        candidatos: list[LotCandidate] = []
        for saldo in uow.balances.list_by_product_branch(product_id, branch_id):
            if saldo["inventory_status"] != InventoryStatus.AVAILABLE.value:
                continue
            if saldo["warehouse_id"] != warehouse_id:
                continue
            if lot_required and not saldo["lot_id"]:
                continue
            libre = _dec(saldo["quantity"]) - _dec(saldo["reserved_quantity"])
            if libre <= 0:
                continue
            lote = lotes.get(saldo["lot_id"]) if saldo["lot_id"] else None
            candidatos.append(LotCandidate(
                lot_id=saldo["lot_id"] or None, available_quantity=libre,
                expiration_date=lote["expiration_date"] if lote else None,
                received_at=(lote.get("received_at") or lote.get("created_at")) if lote else None,
                quality_status=(LotQualityStatus(lote["quality_status"]) if lote
                                else LotQualityStatus.RELEASED),
                location_id=saldo["location_id"] or None))
        return candidatos
