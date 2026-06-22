from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from .states import (
    AdjustmentStatus,
    DeliveryStatus,
    DeliveryType,
    DeliveryWorkflowType,
    normalize_adjustment_status,
    normalize_delivery_type,
    normalize_status,
    normalize_workflow_type,
)


@dataclass(slots=True)
class DeliveryItem:
    id: int | None = None
    delivery_id: int | None = None
    producto_id: int | None = None
    nombre: str = "Producto"
    cantidad: float = 0.0
    precio_unitario: float = 0.0
    subtotal: float = 0.0
    unidad: str = ""
    requested_qty: float | None = None
    prepared_qty: float | None = None
    final_qty: float | None = None
    adjustment_status: AdjustmentStatus = AdjustmentStatus.NONE

    def __post_init__(self) -> None:
        self.adjustment_status = normalize_adjustment_status(self.adjustment_status)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeliveryItem":
        qty = float(data.get("cantidad") or data.get("qty") or 0)
        price = float(data.get("precio_unitario") or data.get("precio") or data.get("unit_price") or 0)
        subtotal = float(data.get("subtotal") or qty * price)
        return cls(
            id=data.get("id"),
            delivery_id=data.get("delivery_id"),
            producto_id=data.get("producto_id") or data.get("product_id"),
            nombre=data.get("nombre") or data.get("producto_nombre") or data.get("name") or "Producto",
            cantidad=qty,
            precio_unitario=price,
            subtotal=subtotal,
            unidad=data.get("unidad") or "",
            requested_qty=data.get("requested_qty"),
            prepared_qty=data.get("prepared_qty"),
            final_qty=data.get("final_qty"),
            adjustment_status=normalize_adjustment_status(data.get("adjustment_status")),
        )

    @property
    def has_pending_adjustment(self) -> bool:
        return self.adjustment_status == AdjustmentStatus.PENDING_CUSTOMER


@dataclass(slots=True)
class DeliveryAdjustment:
    item_id: int
    requested_qty: float
    prepared_qty: float
    unit_price: float
    new_subtotal: float
    diff_qty: float
    tolerance_units: float
    status: AdjustmentStatus
    reason: str = ""
    token: str = ""

    @property
    def requires_customer_approval(self) -> bool:
        return self.status == AdjustmentStatus.PENDING_CUSTOMER


@dataclass(slots=True)
class DeliveryDriver:
    id: int
    nombre: str
    telefono: str = ""
    vehiculo: str = ""
    activo: bool = True


@dataclass(slots=True)
class DeliveryOrder:
    id: int | None = None
    venta_id: int | None = None
    folio: str = ""
    whatsapp_order_id: str | None = None
    cliente_id: int | None = None
    cliente_nombre: str = ""
    cliente_tel: str = ""
    direccion: str = ""
    estado: DeliveryStatus = DeliveryStatus.PENDING
    workflow_type: DeliveryWorkflowType | None = None
    delivery_type: DeliveryType | None = None
    scheduled_at: str | datetime | None = None
    driver_id: int | None = None
    responsable_entrega: str = ""
    total: float = 0.0
    sucursal_id: int = 1
    adjustment_pending: bool = False
    activated: bool = False
    items: list[DeliveryItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.estado = normalize_status(self.estado)
        self.workflow_type = normalize_workflow_type(self.workflow_type)
        self.delivery_type = normalize_delivery_type(self.delivery_type)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeliveryOrder":
        items: Sequence[Mapping[str, Any] | DeliveryItem] = data.get("items") or ()
        parsed_items = [item if isinstance(item, DeliveryItem) else DeliveryItem.from_mapping(item) for item in items]
        return cls(
            id=data.get("id"),
            venta_id=data.get("venta_id"),
            folio=data.get("folio") or "",
            whatsapp_order_id=data.get("whatsapp_order_id"),
            cliente_id=data.get("cliente_id"),
            cliente_nombre=data.get("cliente_nombre") or data.get("cliente") or "",
            cliente_tel=data.get("cliente_tel") or data.get("telefono") or "",
            direccion=data.get("direccion") or data.get("direccion_entrega") or "",
            estado=normalize_status(data.get("estado")),
            workflow_type=normalize_workflow_type(data.get("workflow_type")),
            delivery_type=normalize_delivery_type(data.get("delivery_type") or data.get("tipo_entrega")),
            scheduled_at=data.get("scheduled_at") or data.get("fecha_entrega_programada"),
            driver_id=data.get("driver_id"),
            responsable_entrega=data.get("responsable_entrega") or data.get("responsable") or "",
            total=float(data.get("total") or 0),
            sucursal_id=int(data.get("sucursal_id") or 1),
            adjustment_pending=bool(data.get("adjustment_pending")),
            activated=bool(data.get("activated") or data.get("activated_at")),
            items=parsed_items,
        )

    @property
    def has_pending_adjustment(self) -> bool:
        return self.adjustment_pending or any(item.has_pending_adjustment for item in self.items)

    @property
    def has_responsible_party(self) -> bool:
        return bool(self.responsable_entrega or self.driver_id)
