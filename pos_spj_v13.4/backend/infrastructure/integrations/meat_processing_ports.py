"""Adaptadores REALES de los puertos de Procesamiento Cárnico (Fase 10).

Hasta el 2026-09-19 los cuatro puertos que conectan Cárnico con el resto del
ERP eran nulos (`ports.py`): el consumo nunca descontaba la entrada, las salidas
nunca entraban a existencia, Costos nunca confirmaba y Mermas nunca recibía el
caso. El cierre de toda orden quedaba pendiente para siempre de
"consumos publicados / inventario confirmado / costos notificados".

Cárnico sigue sin escribir tablas ajenas (§39): cada adaptador llama a los
casos de uso del contexto dueño (Inventario, Costos, Mermas).

Permisos: igual que la salida por venta de Ventas y el puente de producción de
Inventario, el movimiento lo autoriza el contexto que lo origina — el operario
ya pasó `PRODUCCION.consumo.capturar` / `PRODUCCION.output.capturar` /
`PRODUCCION.orden.cerrar` en el caso de uso de Cárnico que llama a este puerto.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.meat_processing.ports")


def _cantidad(quantity, weight) -> Decimal:
    """Cárnicos por peso: el kilo ES la cantidad de existencia."""
    peso = Decimal(str(weight or 0))
    return peso if peso > 0 else Decimal(str(quantity or 0))


class CanonicalProductionConsumptionAdapter:
    """`InventoryConsumptionPort` → movimiento `PRODUCTION_CONSUMPTION`.

    `unit_costs`: costo con que sale cada producto (el de Costeo). Con
    `negative_authorized` la salida puede dejar la existencia negativa: sólo si
    otro usuario autorizó producir sin existencia (decisión del usuario).
    """

    def __init__(self, connection, *, branch_id: str, actor_user_id: str,
                 document_id: str, unit_costs: dict | None = None,
                 negative_authorized: bool = False) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor = actor_user_id
        self._document_id = document_id
        self._unit_costs = unit_costs or {}
        self._negative = negative_authorized
        self.last_error: str | None = None

    def post_consumption(self, *, operation_id, product_id, warehouse_id, quantity, weight,
                         lot_id=None, location_id=None) -> str | None:
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        movement = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_CONSUMPTION, branch_id=self._branch_id,
            warehouse_id=warehouse_id, source_module="meat_processing",
            source_document_type="PROCESSING_ORDER", source_document_id=self._document_id,
            operation_id=f"{operation_id}:consume", created_by_user_id=self._actor,
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=_cantidad(quantity, weight),
                lot_id=lot_id, from_location_id=location_id or self._branch_id,
                from_status=InventoryStatus.AVAILABLE, reason_code="PROCESSING_INPUT",
                unit_cost=self._unit_costs.get(product_id))])
        result = PostInventoryMovementUseCase().execute(
            self._conn, movement, actor_user_id=self._actor,
            negative_allowed=self._negative, authorized=self._negative)
        if not result.success:
            self.last_error = result.message
            return None
        return result.entity_id


class CanonicalProductionReceiptAdapter:
    """`InventoryReceiptPort` → lote de producción + `PRODUCTION_OUTPUT`.

    Cada salida entra con su costo REPARTIDO (`unit_costs`) y en un lote de
    producción (`lot_code`); si la entrada venía de un lote, se enlaza la
    genealogía lote origen → lote destino (§13/§19).
    """

    def __init__(self, connection, *, branch_id: str, actor_user_id: str,
                 document_id: str, lot_code: str, unit_costs: dict | None = None,
                 input_lot_ids: tuple[str, ...] = ()) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor = actor_user_id
        self._document_id = document_id
        self._lot_code = lot_code
        self._unit_costs = unit_costs or {}
        self._input_lots = tuple(l for l in input_lot_ids if l)
        self.last_error: str | None = None
        self.lot_ids: dict[str, str] = {}

    def post_output(self, *, operation_id, product_id, warehouse_id, quantity, weight,
                    lot_id=None, location_id=None) -> str | None:
        from backend.application.inventory.use_cases.lot_use_cases import (
            RegisterInventoryLotUseCase,
        )
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.application.inventory.use_cases.register_traceability_link import (
            RegisterTraceabilityLinkUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import (
            InventoryStatus,
            LotOrigin,
            MovementType,
            TraceabilityLinkType,
        )

        if not lot_id:
            lote = RegisterInventoryLotUseCase().execute(
                self._conn, product_id=product_id, lot_code=self._lot_code,
                origin_type=LotOrigin.PRODUCTION,
                operation_id=f"{self._document_id}:lot:{product_id}",
                actor_user_id=self._actor, production_lot_code=self._lot_code,
                origin_document_id=self._document_id, branch_id=self._branch_id)
            lot_id = lote.entity_id if lote.success else None
        if lot_id:
            self.lot_ids[product_id] = lot_id

        movement = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_OUTPUT, branch_id=self._branch_id,
            warehouse_id=warehouse_id, source_module="meat_processing",
            source_document_type="PROCESSING_ORDER", source_document_id=self._document_id,
            operation_id=f"{operation_id}:output", created_by_user_id=self._actor,
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=_cantidad(quantity, weight), lot_id=lot_id,
                to_location_id=location_id or self._branch_id,
                to_status=InventoryStatus.AVAILABLE, reason_code="PROCESSING_OUTPUT",
                unit_cost=self._unit_costs.get(product_id))])
        result = PostInventoryMovementUseCase().execute(
            self._conn, movement, actor_user_id=self._actor)
        if not result.success:
            self.last_error = result.message
            return None
        if lot_id:
            for origen in self._input_lots:
                RegisterTraceabilityLinkUseCase().execute(
                    self._conn, parent_lot_id=origen, child_lot_id=lot_id,
                    link_type=TraceabilityLinkType.PRODUCTION,
                    operation_id=f"{self._document_id}:link:{origen}:{lot_id}",
                    actor_user_id=self._actor, product_id=product_id,
                    source_module="meat_processing", source_document_type="PROCESSING_ORDER",
                    source_document_id=self._document_id)
        return result.entity_id


class ProjectedCostAllocationAdapter:
    """`CostAllocationPort`: el costo ya repartido entra al costo PROMEDIO de
    cada salida, con el contrato con que Producción informa su costo
    (`PRODUCTION_OUTPUT_COSTED` → `ProductCostProjectionHandler`, idempotente).

    `lines`: [{product_id, quantity (kg), unit_cost}] de las salidas buenas.
    Devuelve la referencia del reparto (el cierre la exige) o None si falla.
    """

    def __init__(self, connection, *, lines: list[dict], actor_user_id: str) -> None:
        self._conn = connection
        self._lines = [dict(l) for l in lines if Decimal(str(l.get("quantity") or 0)) > 0]
        self._actor = actor_user_id
        self.last_error: str | None = None

    def request_cost_allocation(self, *, operation_id, processing_order_id,
                                process_type) -> str | None:
        from backend.application.pricing.event_handlers.product_cost_projection_handler import (
            ProductCostProjectionHandler,
        )
        referencia = f"{processing_order_id}:cost"
        try:
            ProductCostProjectionHandler(self._conn).handle({
                "event_id": referencia, "operation_id": referencia, "user_id": self._actor,
                "lines": [{"product_id": l["product_id"], "quantity": str(l["quantity"]),
                           "unit_cost": str(l["unit_cost"])} for l in self._lines]})
        except Exception as exc:  # noqa: BLE001 — el cierre informa el motivo
            logger.exception("costo de la orden %s no proyectado", processing_order_id)
            self.last_error = str(exc)
            return None
        return referencia


class LossesYieldVarianceAdapter:
    """`LossCaseRequestPort` → caso de Mermas por variación de rendimiento.

    Mermas pone la causa (`YIELD_VARIANCE`) y lo registra SIN movimiento de
    inventario: la merma de un despiece ya está en existencias (la entrada se
    consumió completa). `unit_cost`: costo por kg de la entrada, para valuar.
    """

    def __init__(self, connection, *, branch_id: str, warehouse_id: str,
                 actor_user_id: str, unit_cost: Decimal = Decimal("0"),
                 notes: str = "") -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._warehouse_id = warehouse_id
        self._actor = actor_user_id
        self._unit_cost = Decimal(str(unit_cost or 0))
        self._notes = notes
        self.last_error: str | None = None

    def request_loss_case(self, *, operation_id, processing_order_id, product_id,
                          expected_weight, actual_weight, difference_weight, process_type,
                          processing_batch_id=None, lot_id=None, operator_ids=(),
                          equipment_ids=()) -> str | None:
        from backend.domain.losses.entities import LossCase, LossLine
        from backend.domain.losses.enums import LossClassificationCode, LossOrigin
        from backend.domain.losses.events import LossEvents, build_loss_event
        from backend.infrastructure.persistence.production_loss_repository import (
            ProductionLossRepository,
        )

        repo = ProductionLossRepository(self._conn)
        causa = repo.yield_variance_reason()
        if not causa:
            self.last_error = ("Mermas no tiene configurada la causa «Variación de "
                               "rendimiento»; no se puede abrir el caso")
            return None
        peso = abs(Decimal(str(difference_weight or 0)))
        if peso <= 0:
            return None
        caso = LossCase(
            id=new_uuid(), operation_id=new_uuid(), branch_id=self._branch_id,
            warehouse_id=self._warehouse_id, reported_by_user_id=self._actor,
            classification=LossClassificationCode.YIELD_VARIANCE, origin=LossOrigin.PRODUCTION,
            reason_id=causa[1], source_document_id=processing_order_id,
            notes=(self._notes or "Variación de rendimiento en orden de despiece")
            + f" — esperado {expected_weight} kg, real {actual_weight} kg")
        caso.add_line(LossLine(id=new_uuid(), product_id=product_id, weight=peso, unit="kg",
                               unit_cost=self._unit_cost))
        caso.submit(actor_user_id=self._actor)
        evento = build_loss_event(
            LossEvents.YIELD_VARIANCE_DETECTED, operation_id=caso.operation_id,
            entity_id=caso.id, branch_id=self._branch_id, warehouse_id=self._warehouse_id,
            user_id=self._actor, production_id=processing_order_id,
            loss_weight=str(peso))
        repo.record_production_variance_case(caso, event=evento)
        return caso.id
