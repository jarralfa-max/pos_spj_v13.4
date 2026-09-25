"""External ports Meat Processing use cases depend on but does not implement
(§40: Productos owns recipe/BOM/cutting-scheme/yield-profile master data;
Procesamiento only ever consumes a frozen snapshot of it, never mutates it).

`RecipeSnapshotPort` resolves the FULL productive definition
(`ProcessingRecipeSnapshot`, domain) that `ReleaseProcessingOrderUseCase`
freezes for an order. The real implementation is
`integrations/products_recipe_snapshot_adapter.py`. There is no permissive
default any more: an order whose process requires master data cannot release
without it (`ProcessingMasterDataRequirementPolicy`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol

from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    ProcessingRecipeSnapshot,
)
from backend.domain.meat_processing.enums import ProcessType


class RecipeSnapshotPort(Protocol):
    def resolve(
        self, *, target_product_id: str, process_type: ProcessType
    ) -> ProcessingRecipeSnapshot | None: ...


class NullRecipeSnapshotPort:
    """No Products integration: resolves nothing. The master-data policy then
    decides — a process that needs a definition cannot release, one that needs
    none (e.g. conditioning with no requirement configured) is told explicitly
    that its definition could not be resolved."""

    def resolve(self, *, target_product_id: str, process_type: ProcessType
                ) -> ProcessingRecipeSnapshot | None:
        return None


class InventoryConsumptionPort(Protocol):
    """§39: Procesamiento nunca escribe movimientos de inventario ni actualiza
    balances directamente — solo solicita el movimiento a Inventario y guarda
    el ``inventory_operation_id`` que Inventario le devuelve. This is that
    request boundary for material consumption."""

    def post_consumption(
        self,
        *,
        operation_id: str,
        product_id: str,
        warehouse_id: str,
        quantity: Any,
        weight: Any,
        lot_id: str | None = None,
        location_id: str | None = None,
        reservation_id: str | None = None,
    ) -> str | None: ...


class NullInventoryConsumptionPort:
    """Default port: no Inventory integration wired yet. Returns None rather
    than fabricating an ``inventory_operation_id`` — PostMaterialConsumptionUseCase
    treats that as "integration pending", never as a silent success, so a
    consumption is never marked POSTED without Inventory actually having
    confirmed the movement."""

    def post_consumption(
        self,
        *,
        operation_id: str,
        product_id: str,
        warehouse_id: str,
        quantity: Any,
        weight: Any,
        lot_id: str | None = None,
        location_id: str | None = None,
        reservation_id: str | None = None,
    ) -> str | None:
        return None


class InventoryReceiptPort(Protocol):
    """§39/§10 (Outputs): Procesamiento nunca da de alta stock directamente —
    solicita a Inventario que reciba el output producido y guarda el
    ``inventory_operation_id`` que Inventario devuelve.

    `quality_hold=True`: el producto está sujeto a inspección, así que entra a
    existencia RETENIDO (estado QUARANTINED), nunca disponible. Sólo Calidad lo
    libera. Cada método recibe el `operation_id` exacto del paso (UUIDv7): el
    adaptador no deriva identidades concatenando cadenas."""

    def register_output_lot(
        self, *, operation_id: str, product_id: str, lot_code: str, quality_hold: bool,
    ) -> str | None: ...

    def post_output(
        self,
        *,
        operation_id: str,
        product_id: str,
        warehouse_id: str,
        quantity: Any,
        weight: Any,
        lot_id: str | None = None,
        location_id: str | None = None,
        quality_hold: bool = False,
    ) -> str | None: ...

    def link_lot_genealogy(
        self, *, operation_id: str, parent_lot_id: str, child_lot_id: str, product_id: str,
    ) -> str | None: ...


class NullInventoryReceiptPort:
    """Default port: no Inventory integration wired yet. Returns None rather
    than fabricating an ``inventory_operation_id`` — mirrors
    NullInventoryConsumptionPort's honesty contract."""

    def register_output_lot(
        self, *, operation_id: str, product_id: str, lot_code: str, quality_hold: bool,
    ) -> str | None:
        return None

    def post_output(
        self,
        *,
        operation_id: str,
        product_id: str,
        warehouse_id: str,
        quantity: Any,
        weight: Any,
        lot_id: str | None = None,
        location_id: str | None = None,
        quality_hold: bool = False,
    ) -> str | None:
        return None

    def link_lot_genealogy(
        self, *, operation_id: str, parent_lot_id: str, child_lot_id: str, product_id: str,
    ) -> str | None:
        return None


@dataclass(frozen=True)
class ReservedStock:
    """Un saldo que Inventario retuvo para un requerimiento: lote y ubicación
    los eligió Inventario, no Procesamiento."""

    reservation_id: str
    lot_id: str | None
    location_id: str | None
    quantity: Decimal


@dataclass(frozen=True)
class ReservationOutcome:
    lines: tuple[ReservedStock, ...] = ()
    available: Decimal | None = None
    error: str | None = None
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.lines) and self.error is None


class MaterialReservationPort(Protocol):
    """§15/§16: la reserva de insumos vive en Inventario. Procesamiento pide y
    guarda lo que Inventario reservó; nunca lleva una reserva paralela."""

    def reserve(
        self, *, operation_id: str, material_requirement_id: str, product_id: str,
        branch_id: str, warehouse_id: str, quantity: Decimal, lot_required: bool,
    ) -> ReservationOutcome: ...

    def release(self, *, operation_id: str, reservation_id: str, reason: str) -> bool: ...


class NullMaterialReservationPort:
    """Sin Inventario integrado no hay reserva: nunca se finge una."""

    def reserve(self, *, operation_id, material_requirement_id, product_id, branch_id,
                warehouse_id, quantity, lot_required) -> ReservationOutcome:
        return ReservationOutcome(error="Inventario no está integrado; no se puede reservar",
                                  error_code="INVENTORY_INTEGRATION_PENDING")

    def release(self, *, operation_id, reservation_id, reason) -> bool:
        return False


class LossCaseRequestPort(Protocol):
    """§27: when a yield reconciliation lands OUT_OF_TOLERANCE/CRITICAL,
    Procesamiento requests a loss case from Mermas/Losses — it never classifies
    or records the loss itself (that's Losses' job; `LossOrigin.PRODUCTION`/
    `.CUTTING` already exist there precisely to receive this). Returns the
    created loss case id, or None if Losses is not wired yet."""

    def request_loss_case(
        self,
        *,
        operation_id: str,
        processing_order_id: str,
        product_id: str,
        expected_weight: Any,
        actual_weight: Any,
        difference_weight: Any,
        process_type: ProcessType,
        processing_batch_id: str | None = None,
        lot_id: str | None = None,
        operator_ids: tuple[str, ...] = (),
        equipment_ids: tuple[str, ...] = (),
    ) -> str | None: ...


class NullLossCaseRequestPort:
    """Default port: no Losses integration wired yet. Returns None rather than
    fabricating a loss_case_id — mirrors the other Null ports' honesty
    contract; RequestLossCaseForYieldVarianceUseCase treats it as pending."""

    def request_loss_case(
        self,
        *,
        operation_id: str,
        processing_order_id: str,
        product_id: str,
        expected_weight: Any,
        actual_weight: Any,
        difference_weight: Any,
        process_type: ProcessType,
        processing_batch_id: str | None = None,
        lot_id: str | None = None,
        operator_ids: tuple[str, ...] = (),
        equipment_ids: tuple[str, ...] = (),
    ) -> str | None:
        return None


class QualityInspectionPort(Protocol):
    """§28/§44: Procesamiento solicita inspección; nunca libera ni bloquea un
    output por su cuenta — esa decisión es de Calidad, comunicada de vuelta
    (síncronamente aquí, vía evento en integración real) y solo *registrada*
    por `RecordQualityDecisionUseCase`."""

    def request_inspection(
        self,
        *,
        operation_id: str,
        process_output_id: str,
        product_id: str,
        lot_id: str | None = None,
    ) -> str | None: ...


class NullQualityInspectionPort:
    """Default port: no Quality integration wired yet. Returns None rather
    than fabricating an inspection_request_id."""

    def request_inspection(
        self,
        *,
        operation_id: str,
        process_output_id: str,
        product_id: str,
        lot_id: str | None = None,
    ) -> str | None:
        return None


class CostAllocationPort(Protocol):
    """§6/§46: "Costos administra... costo de transformación" — Procesamiento
    never computes or posts a peso/costo, it only requests that Costos
    allocate the transformation cost for a completed order once every
    consumption/output has been captured, and gates the close on Costos
    confirming (`OrderClosingPolicy`'s ``costs_notified`` precondition)."""

    def request_cost_allocation(
        self, *, operation_id: str, processing_order_id: str, process_type: ProcessType,
    ) -> str | None: ...

    def preflight(self, *, processing_order_id: str, process_type: ProcessType,
                  consumed: list[tuple[str, Decimal, str | None]],
                  produced: list[tuple[str, str, Decimal]]) -> tuple[str, str] | None:
        """¿Costos podrá costear estos hechos? None = sí; si no, (código, motivo).
        Se pregunta ANTES de mover existencia. Costos decide; aquí no se calcula."""
        ...


class NullCostAllocationPort:
    """Default port: no Costing integration wired yet. Returns None rather
    than fabricating a cost_allocation_reference — mirrors every other Null
    port's honesty contract; CloseProcessingOrderUseCase treats it as one
    more unmet close precondition, never a silent pass."""

    def request_cost_allocation(
        self, *, operation_id: str, processing_order_id: str, process_type: ProcessType,
    ) -> str | None:
        return None

    def preflight(self, *, processing_order_id, process_type, consumed, produced):
        return ("COSTING_NOT_CONNECTED", "Costos no está conectado: la orden no podría cerrarse.")


class NotificationPort(Protocol):
    """§20/§60: Procesamiento nunca envía un WhatsApp/notificación
    directamente — pide al microservicio de notificaciones que lo haga y
    guarda la referencia que devuelve. Mismo boundary que el resto de los
    puertos: Procesamiento describe la alerta, nunca decide cómo se entrega
    ni a quién exactamente (eso es del lado de notificaciones/WhatsApp)."""

    def send_alert(
        self,
        *,
        operation_id: str,
        alert_type: str,
        severity: str,
        message: str,
        branch_id: str,
    ) -> str | None: ...


class NullNotificationPort:
    """Default port: no notification/WhatsApp integration wired yet. Returns
    None rather than fabricating a notification_reference — mirrors every
    other Null port's honesty contract."""

    def send_alert(
        self,
        *,
        operation_id: str,
        alert_type: str,
        severity: str,
        message: str,
        branch_id: str,
    ) -> str | None:
        return None


@dataclass
class ExecutionPorts:
    """Adaptadores hacia los contextos dueños, para UNA orden y UN operador."""

    consumption: object
    receipt: object
    reservation: object
    quality: object
    losses: object
    costing: object
    #: product_id → ubicación de destino que resuelve Inventario (o excepción).
    output_location: Callable[[str], str]


class QualityDecisionReadPort(Protocol):
    """Lectura de lo que CALIDAD decidió (contrato de lectura de Calidad).

    `decision_of` devuelve la inspección decidida — ``subject_id``,
    ``source_module``, ``status`` y ``decided_by_user_id`` — o None. Procesamiento
    sólo registra en su output una decisión que exista así en Calidad."""

    def decision_of(self, inspection_id: str) -> dict | None: ...


class NullQualityDecisionReadPort:
    """Sin Calidad conectada no hay decisión que confirmar: nunca se registra."""

    def decision_of(self, inspection_id: str) -> dict | None:
        return None

