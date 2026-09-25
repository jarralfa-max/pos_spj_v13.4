"""Adaptadores REALES de los puertos de Procesamiento Cárnico.

Cárnico no escribe tablas ajenas (§39): cada adaptador llama al caso de uso del
contexto dueño. Reglas que aquí se hacen cumplir y que antes no:

- AUTORIZACIÓN REAL. Cada caso de uso de Inventario se construye con la
  concesión que Inventario declara para `meat_processing`
  (`integration_grants.MEAT_PROCESSING_GRANT`), atada al operador que ejecuta,
  y con un alcance limitado a la sucursal y el almacén de la orden. Nunca con
  `permissive_for_tests()`.
- UUIDv7 PURO. Cada llamada recibe el `operation_id` exacto del paso (la
  bitácora de la ejecución lo genera una vez y lo reutiliza al reintentar). No
  se derivan identidades concatenando cadenas.
- SIN INVENTARIO NEGATIVO. Procesamiento no fabrica existencia: el consumo sale
  de lo que Inventario reservó y nunca se autoriza dejar saldo negativo.
- SIN SUCURSAL COMO UBICACIÓN. El consumo sale de la ubicación que Inventario
  reservó; la recepción entra a la ubicación que Inventario resolvió. Si falta,
  se falla; no se usa la sucursal en su lugar.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.inventory.integration_grants import (
    inventory_policy_for,
    inventory_scope_for,
)
from backend.application.meat_processing.ports import ReservationOutcome, ReservedStock
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.meat_processing.ports")

SOURCE_MODULE = "meat_processing"


def _cantidad(quantity, weight) -> Decimal:
    """Cárnicos por peso: el kilo ES la cantidad de existencia."""
    peso = Decimal(str(weight or 0))
    return peso if peso > 0 else Decimal(str(quantity or 0))


class _InventoryIntegration:
    """Política y alcance de Inventario para UNA orden y UN operador."""

    def __init__(self, connection, *, branch_id: str, warehouse_id: str,
                 actor_user_id: str, document_id: str) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._warehouse_id = warehouse_id
        self._actor = actor_user_id
        self._document_id = document_id
        self.policy, self.checker = inventory_policy_for(SOURCE_MODULE, actor_user_id)
        self.scope = inventory_scope_for(actor_user_id=actor_user_id, branch_id=branch_id,
                                         warehouse_id=warehouse_id)
        self.last_error: str | None = None


class InventoryMaterialReservationAdapter(_InventoryIntegration):
    """`MaterialReservationPort` → `ReserveStockForProductionUseCase`."""

    def __init__(self, connection, *, branch_id: str, warehouse_id: str,
                 actor_user_id: str, document_id: str, strategy=None) -> None:
        super().__init__(connection, branch_id=branch_id, warehouse_id=warehouse_id,
                         actor_user_id=actor_user_id, document_id=document_id)
        #: None = la que tenga configurada Inventario (FEFO si nada).
        self._strategy = strategy

    def reserve(self, *, operation_id, material_requirement_id, product_id, branch_id,
                warehouse_id, quantity, lot_required) -> ReservationOutcome:
        from backend.application.inventory.use_cases.production_reservation_use_cases import (
            ReserveStockForProductionUseCase,
        )
        r = ReserveStockForProductionUseCase(self.policy).execute(
            self._conn, product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
            quantity=quantity, source_document_id=material_requirement_id,
            operation_id=operation_id, actor_user_id=self._actor, lot_required=lot_required,
            strategy=self._strategy, context=self.scope)
        if not r.success:
            self.last_error = r.message
            disponible = r.data.get("available")
            return ReservationOutcome(
                available=Decimal(str(disponible)) if disponible is not None else None,
                error=r.message, error_code=r.error_code)
        return ReservationOutcome(lines=tuple(
            ReservedStock(l.reservation_id, l.lot_id, l.location_id, Decimal(str(l.quantity)))
            for l in r.data.get("lines", ())))

    def release(self, *, operation_id, reservation_id, reason) -> bool:
        from backend.application.inventory.use_cases.reservation_use_cases import (
            ReleaseReservationUseCase,
        )
        r = ReleaseReservationUseCase(self.policy).execute(
            self._conn, reservation_id=reservation_id, operation_id=operation_id,
            actor_user_id=self._actor, reason=reason, context=self.scope)
        if not r.success:
            self.last_error = r.message
        return bool(r.success)


class CanonicalProductionConsumptionAdapter(_InventoryIntegration):
    """`InventoryConsumptionPort` → `PRODUCTION_CONSUMPTION` + cumplir la reserva.

    Mismo orden que la salida por venta: primero baja la existencia, después se
    suelta la retención. Si el movimiento falla, la reserva sigue puesta.
    """

    def post_consumption(self, *, operation_id, product_id, warehouse_id, quantity, weight,
                         lot_id=None, location_id=None, reservation_id=None) -> str | None:
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.application.inventory.use_cases.reservation_use_cases import (
            FulfillReservationUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        if reservation_id is None:
            self.last_error = ("El consumo no tiene una reserva de Inventario: prepara la "
                               "orden para reservar sus insumos antes de ejecutar.")
            return None
        movement = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_CONSUMPTION, branch_id=self._branch_id,
            warehouse_id=warehouse_id, source_module=SOURCE_MODULE,
            source_document_type="PROCESSING_ORDER", source_document_id=self._document_id,
            operation_id=operation_id, created_by_user_id=self._actor,
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=_cantidad(quantity, weight),
                lot_id=lot_id, from_location_id=location_id,
                from_status=InventoryStatus.AVAILABLE, reason_code="PROCESSING_INPUT")])
        result = PostInventoryMovementUseCase(self.policy).execute(
            self._conn, movement, actor_user_id=self._actor, negative_allowed=False,
            authorized=False, context=self.scope)
        if not result.success:
            self.last_error = result.message
            return None
        cumplir = FulfillReservationUseCase(self.policy).execute(
            self._conn, reservation_id=reservation_id, operation_id=new_uuid(),
            actor_user_id=self._actor, context=self.scope)
        if not cumplir.success:
            self.last_error = cumplir.message
            return None
        return result.entity_id


class CanonicalProductionReceiptAdapter(_InventoryIntegration):
    """`InventoryReceiptPort` → lote de producción + `PRODUCTION_OUTPUT` + genealogía.

    Un producto sujeto a inspección entra RETENIDO: lote en cuarentena y saldo
    QUARANTINED en la ubicación resuelta. Output, lote y saldo dicen lo mismo;
    sólo Calidad lo pasa a disponible.
    """

    def register_output_lot(self, *, operation_id, product_id, lot_code,
                            quality_hold) -> str | None:
        from backend.application.inventory.use_cases.lot_use_cases import (
            RegisterInventoryLotUseCase,
        )
        from backend.domain.inventory.enums import LotOrigin, LotQualityStatus

        lote = RegisterInventoryLotUseCase(self.policy).execute(
            self._conn, product_id=product_id, lot_code=lot_code,
            origin_type=LotOrigin.PRODUCTION, operation_id=operation_id,
            actor_user_id=self._actor, context=self.scope, production_lot_code=lot_code,
            origin_document_id=self._document_id, branch_id=self._branch_id,
            quality_status=(LotQualityStatus.QUARANTINED if quality_hold
                            else LotQualityStatus.RELEASED))
        if not lote.success:
            self.last_error = lote.message
            return None
        return lote.entity_id

    def post_output(self, *, operation_id, product_id, warehouse_id, quantity, weight,
                    lot_id=None, location_id=None, quality_hold=False) -> str | None:
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        if not location_id:
            self.last_error = "Inventario no resolvió la ubicación de destino del output"
            return None
        movement = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_OUTPUT, branch_id=self._branch_id,
            warehouse_id=warehouse_id, source_module=SOURCE_MODULE,
            source_document_type="PROCESSING_ORDER", source_document_id=self._document_id,
            operation_id=operation_id, created_by_user_id=self._actor,
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=_cantidad(quantity, weight), lot_id=lot_id,
                to_location_id=location_id,
                to_status=(InventoryStatus.QUARANTINED if quality_hold
                           else InventoryStatus.AVAILABLE),
                reason_code="PROCESSING_OUTPUT")])
        result = PostInventoryMovementUseCase(self.policy).execute(
            self._conn, movement, actor_user_id=self._actor, context=self.scope)
        if not result.success:
            self.last_error = result.message
            return None
        return result.entity_id

    def link_lot_genealogy(self, *, operation_id, parent_lot_id, child_lot_id,
                           product_id) -> str | None:
        from backend.application.inventory.use_cases.register_traceability_link import (
            RegisterTraceabilityLinkUseCase,
        )
        from backend.domain.inventory.enums import TraceabilityLinkType

        r = RegisterTraceabilityLinkUseCase(self.policy).execute(
            self._conn, parent_lot_id=parent_lot_id, child_lot_id=child_lot_id,
            link_type=TraceabilityLinkType.PRODUCTION, operation_id=operation_id,
            actor_user_id=self._actor, product_id=product_id, source_module=SOURCE_MODULE,
            source_document_type="PROCESSING_ORDER", source_document_id=self._document_id)
        if not r.success:
            self.last_error = r.message
            return None
        return r.entity_id or child_lot_id


class CostingAllocationAdapter:
    """`CostAllocationPort` → Costos (`AllocateProductionCostUseCase`).

    Procesamiento no calcula costos: aquí sólo arma los HECHOS que ya registró
    (consumos posteados, salidas producidas) y pide el costeo. Costos decide el
    costo de entrada, el método de reparto y la merma valorizada; devuelve la
    referencia de la asignación. `dispatch` entrega los hechos que Costos dejó
    en su outbox (Precios y Finanzas) sin esperar a otro proceso.
    """

    def __init__(self, connection, *, actor_user_id: str, branch_id: str,
                 dispatch=None) -> None:
        self._conn = connection
        self._actor = actor_user_id
        self._branch_id = branch_id
        self._dispatch = dispatch
        self.last_error: str | None = None

    def request_cost_allocation(self, *, operation_id, processing_order_id,
                                process_type) -> str | None:
        from backend.application.costing.processing_costing import (
            AllocateProductionCostUseCase,
            ConsumedMaterial,
            ProducedOutput,
            ProductionCostFacts,
            costing_policy_for,
        )
        from backend.domain.meat_processing.enums import ConsumptionStatus
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )

        uow = MeatProcessingUnitOfWork(self._conn)
        hechos = ProductionCostFacts(
            source_module=SOURCE_MODULE, processing_order_id=processing_order_id,
            branch_id=self._branch_id, process_type=getattr(process_type, "value", process_type),
            consumed=tuple(
                ConsumedMaterial(c.product_id, _cantidad(c.actual_quantity, c.actual_weight),
                                 c.lot_id)
                for c in uow.consumptions.list_by_order(processing_order_id)
                if c.status is ConsumptionStatus.POSTED),
            produced=tuple(
                ProducedOutput(o.product_id, o.output_type.value,
                               _cantidad(o.quantity, o.weight), o.lot_id)
                for o in uow.outputs.list_by_order(processing_order_id)))
        r = AllocateProductionCostUseCase(costing_policy_for(SOURCE_MODULE, self._actor)).execute(
            self._conn, hechos, operation_id=operation_id, actor_user_id=self._actor)
        if not r.success:
            self.last_error = r.message
            return None
        if self._dispatch is not None:
            try:
                self._dispatch(self._conn)
            except Exception:  # noqa: BLE001 — queda pendiente en el outbox de Costos
                logger.exception("costeo de %s: hechos pendientes de entregar",
                                 processing_order_id)
        return r.allocation_id

    def preflight(self, *, processing_order_id, process_type, consumed, produced):
        """Pregunta a Costos si puede costear lo que se va a producir, sin
        escribir nada (mismo cálculo que el costeo real)."""
        from backend.application.costing.processing_costing import (
            AllocateProductionCostUseCase,
            ConsumedMaterial,
            ProducedOutput,
            ProductionCostFacts,
            costing_policy_for,
        )

        hechos = ProductionCostFacts(
            source_module=SOURCE_MODULE, processing_order_id=processing_order_id,
            branch_id=self._branch_id, process_type=getattr(process_type, "value", process_type),
            consumed=tuple(ConsumedMaterial(pid, qty, lot) for pid, qty, lot in consumed),
            produced=tuple(ProducedOutput(pid, tipo, qty, None) for pid, tipo, qty in produced))
        r = AllocateProductionCostUseCase(costing_policy_for(SOURCE_MODULE, self._actor)).preview(
            self._conn, hechos, actor_user_id=self._actor)
        return None if r.success else (r.error_code, r.message)


class LossesYieldVarianceAdapter:
    """`LossCaseRequestPort` → Mermas (`RequestYieldVarianceLossCaseUseCase`).

    Procesamiento pide el caso; Mermas clasifica, valúa y lo registra sin
    movimiento de inventario (la existencia ya se movió al consumir y producir).
    """

    def __init__(self, connection, *, branch_id: str, warehouse_id: str,
                 actor_user_id: str, notes: str = "") -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._warehouse_id = warehouse_id
        self._actor = actor_user_id
        self._notes = notes
        self.last_error: str | None = None

    def request_loss_case(self, *, operation_id, processing_order_id, product_id,
                          expected_weight, actual_weight, difference_weight, process_type,
                          processing_batch_id=None, lot_id=None, operator_ids=(),
                          equipment_ids=()) -> str | None:
        from backend.application.losses.yield_variance_case import (
            RequestYieldVarianceLossCaseUseCase,
            losses_policy_for,
        )
        r = RequestYieldVarianceLossCaseUseCase(losses_policy_for(SOURCE_MODULE, self._actor)).execute(
            self._conn, operation_id=operation_id, actor_user_id=self._actor,
            branch_id=self._branch_id, warehouse_id=self._warehouse_id,
            source_document_id=processing_order_id, product_id=product_id,
            expected_weight=expected_weight, actual_weight=actual_weight,
            difference_weight=difference_weight, lot_id=lot_id, notes=self._notes)
        if r.case_id is None:
            self.last_error = r.message
        return r.case_id


class QualityInspectionRequestAdapter:
    """`QualityInspectionPort` → Calidad (`RequestOutputInspectionUseCase`).

    Procesamiento sólo PIDE la inspección de un output retenido; la decisión la
    toma un inspector en Calidad, que no puede ser quien produjo.
    """

    def __init__(self, connection, *, branch_id: str, warehouse_id: str,
                 actor_user_id: str, document_id: str, produced_by_user_id: str) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._warehouse_id = warehouse_id
        self._actor = actor_user_id
        self._document_id = document_id
        self._produced_by = produced_by_user_id
        self.last_error: str | None = None

    def request_inspection(self, *, operation_id, process_output_id, product_id,
                           lot_id=None) -> str | None:
        from backend.application.quality.output_inspection import (
            RequestOutputInspectionUseCase,
            quality_policy_for,
        )
        r = RequestOutputInspectionUseCase(quality_policy_for(SOURCE_MODULE, self._actor)).execute(
            self._conn, operation_id=operation_id, actor_user_id=self._actor,
            source_module=SOURCE_MODULE, source_document_id=self._document_id,
            subject_id=process_output_id, product_id=product_id, lot_id=lot_id,
            branch_id=self._branch_id, warehouse_id=self._warehouse_id,
            produced_by_user_id=self._produced_by)
        if not r.success:
            self.last_error = r.message
            return None
        return r.inspection_id


class QualityDecisionReadAdapter:
    """`QualityDecisionReadPort` → lo que Calidad guardó de su inspección."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def decision_of(self, inspection_id: str) -> dict | None:
        from backend.infrastructure.db.repositories.quality.inspection_repository import (
            InspectionRepository,
        )
        inspeccion = InspectionRepository(self._conn).get(inspection_id)
        if inspeccion is None:
            return None
        return {"subject_id": inspeccion.subject_id, "source_module": inspeccion.source_module,
                "status": inspeccion.status,
                "decided_by_user_id": inspeccion.decided_by_user_id}


class ProcessingOrderFolioAdapter:
    """Folio humano de la orden: ``OP-<código de sucursal>-00001``.

    El código es el de la sucursal en Configuración → Empresa y sucursales
    (`branch_profiles.code`, único). El consecutivo es el contador seguro del
    sistema (`document_number_sequences`, uno por prefijo ``OP-<código>``, sin
    reinicio), reservado en la transacción de quien crea la orden.
    """

    DIGITS = 5

    def __init__(self, connection) -> None:
        self._conn = connection
        self.last_error: str | None = None

    def next_folio(self, branch_id: str) -> str | None:
        from backend.domain.document_output.entities.document_number_sequence import (
            DocumentNumberSequence,
        )
        from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (  # noqa: E501
            SqliteDocumentNumberSequenceRepository,
        )

        import sqlite3

        try:
            fila = self._conn.execute("SELECT code FROM branch_profiles WHERE branch_id=?",
                                      (branch_id,)).fetchone()
        except sqlite3.OperationalError:
            fila = None                     # sin perfiles de sucursal: no hay código
        codigo = (str(fila[0]).strip().upper() if fila and fila[0] else "")
        if not codigo:
            self.last_error = ("La sucursal no tiene código: regístralo en Configuración → "
                               "Empresa y sucursales.")
            return None
        prefijo = f"OP-{codigo}"
        repo = SqliteDocumentNumberSequenceRepository(self._conn)
        secuencia = repo.get_by_prefix(prefijo)
        if secuencia is None:
            secuencia = DocumentNumberSequence.create(prefix=prefijo)
            repo.save(secuencia)
        numero = repo.reserve_and_get(secuencia.id, period_key="")
        return f"{prefijo}-{numero:0{self.DIGITS}d}"

