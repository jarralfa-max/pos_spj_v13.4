"""External ports Meat Processing use cases depend on but does not implement
(§40: Productos owns recipe/BOM/cutting-scheme/yield-profile master data;
Procesamiento only ever consumes a frozen snapshot of it, never mutates it).

`RecipeSnapshotPort` is the contract a real Products integration will
implement later (`ActiveRecipeQueryService`, `RecipeVersionSnapshotQueryService`,
`ActiveYieldProfileQueryService`, `ActiveCuttingSchemeQueryService` per §40) —
PROC-6 only defines the shape and ships a no-op default so
`ReleaseProcessingOrderUseCase` works standalone until that integration exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.domain.meat_processing.enums import ProcessType


@dataclass(frozen=True)
class RecipeSnapshot:
    """§14: everything that must be frozen at release time so a later active-
    version change in Products never alters an order already in flight."""
    recipe_version_id: str | None = None
    cutting_scheme_version_id: str | None = None
    yield_profile_version_id: str | None = None
    components: tuple[dict[str, Any], ...] = ()
    outputs: tuple[dict[str, Any], ...] = ()
    units: dict[str, Any] = field(default_factory=dict)
    factors: dict[str, Any] = field(default_factory=dict)
    yield_tolerances: dict[str, Any] = field(default_factory=dict)
    technical_parameters: dict[str, Any] = field(default_factory=dict)
    packaging: dict[str, Any] = field(default_factory=dict)
    quality_profile: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "recipe_version_id": self.recipe_version_id,
            "cutting_scheme_version_id": self.cutting_scheme_version_id,
            "yield_profile_version_id": self.yield_profile_version_id,
            "components": list(self.components),
            "outputs": list(self.outputs),
            "units": self.units,
            "factors": self.factors,
            "yield_tolerances": self.yield_tolerances,
            "technical_parameters": self.technical_parameters,
            "packaging": self.packaging,
            "quality_profile": self.quality_profile,
        }


class RecipeSnapshotPort(Protocol):
    def resolve(
        self, *, target_product_id: str, process_type: ProcessType
    ) -> RecipeSnapshot | None: ...


class NullRecipeSnapshotPort:
    """Default port: no recipe integration wired yet. Orders release with an
    empty snapshot (all version ids stay None) rather than failing — a process
    like PACKAGING may legitimately have no recipe/cutting-scheme at all."""

    def resolve(self, *, target_product_id: str, process_type: ProcessType
                ) -> RecipeSnapshot | None:
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
    ) -> str | None:
        return None


class InventoryReceiptPort(Protocol):
    """§39/§10 (Outputs): Procesamiento nunca da de alta stock directamente —
    solicita a Inventario que reciba el output producido y guarda el
    ``inventory_operation_id`` que Inventario devuelve. Outputs bloqueados por
    calidad (`quality_status != RELEASED`) no deben llegar a este puerto —
    esa decisión vive en la política de captura de outputs, no aquí."""

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
    ) -> str | None: ...


class NullInventoryReceiptPort:
    """Default port: no Inventory integration wired yet. Returns None rather
    than fabricating an ``inventory_operation_id`` — mirrors
    NullInventoryConsumptionPort's honesty contract."""

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
    ) -> str | None:
        return None


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


class NullCostAllocationPort:
    """Default port: no Costing integration wired yet. Returns None rather
    than fabricating a cost_allocation_reference — mirrors every other Null
    port's honesty contract; CloseProcessingOrderUseCase treats it as one
    more unmet close precondition, never a silent pass."""

    def request_cost_allocation(
        self, *, operation_id: str, processing_order_id: str, process_type: ProcessType,
    ) -> str | None:
        return None


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
