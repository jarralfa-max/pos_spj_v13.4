"""DeliverySettingsPresenter (PASS 6) — Configuración de Pedidos/Reparto: zonas
de entrega.

Lee con `DeliveryZonesQueryService` y escribe sólo por los casos de uso de
`zone_use_cases`, que revalidan el permiso. `can_manage()` sólo decide qué botones
se habilitan; no autoriza nada por sí mismo.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.queries.delivery_zones_query_service import (
    DeliveryZoneRow,
    DeliveryZonesQueryService,
)
from backend.application.orders_delivery.use_cases.zone_use_cases import (
    CreateDeliveryZoneUseCase,
    SetDeliveryZoneActiveUseCase,
    UpdateDeliveryZoneUseCase,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
    OrdersTableModel,
)


def _dinero(valor) -> str:
    return f"${Decimal(str(valor)):,.2f}" if valor not in (None, "") else "—"


class DeliverySettingsPresenter:
    def __init__(self, connection, *, branch_id: str, actor_user_id: str | None,
                 authorization=None) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor_user_id = actor_user_id or ""
        self._authorization = authorization
        self._zonas: dict[str, DeliveryZoneRow] = {}

    def can_manage(self) -> bool:
        return bool(
            self._authorization is not None and self._actor_user_id
            and self._authorization.has_permission(
                self._actor_user_id, OrdersDeliveryPermissions.SETTINGS_MANAGE))

    def zones(self) -> OrdersTableModel:
        filas = DeliveryZonesQueryService(self._conn).list_for_branch(self._branch_id)
        self._zonas = {fila.id: fila for fila in filas}
        return OrdersTableModel(
            rows=[
                [
                    fila.name, ", ".join(fila.postal_codes), _dinero(fila.minimum_order),
                    _dinero(fila.delivery_fee), _dinero(fila.free_delivery_threshold),
                    f"{fila.estimated_minutes} min" if fila.estimated_minutes else "—",
                    f"{fila.maximum_distance_km} km" if fila.maximum_distance_km else "—",
                    "Activa" if fila.active else "Inactiva",
                ]
                for fila in filas
            ],
            row_ids=[fila.id for fila in filas], total=len(filas))

    def zone(self, zone_id: str | None) -> DeliveryZoneRow | None:
        return self._zonas.get(zone_id) if zone_id else None

    def create_zone(self, data: dict) -> tuple[bool, str]:
        result = CreateDeliveryZoneUseCase(self._authorization).execute(
            self._conn, branch_id=self._branch_id, actor_user_id=self._actor_user_id,
            operation_id=new_uuid(), **self._campos(data))
        return result.success, result.message

    def update_zone(self, zone_id: str, data: dict) -> tuple[bool, str]:
        result = UpdateDeliveryZoneUseCase(self._authorization).execute(
            self._conn, zone_id=zone_id, branch_id=self._branch_id,
            actor_user_id=self._actor_user_id, operation_id=new_uuid(), **self._campos(data))
        return result.success, result.message

    def set_zone_active(self, zone_id: str, active: bool) -> tuple[bool, str]:
        result = SetDeliveryZoneActiveUseCase(self._authorization).execute(
            self._conn, zone_id=zone_id, branch_id=self._branch_id, active=active,
            actor_user_id=self._actor_user_id, operation_id=new_uuid())
        return result.success, result.message

    @staticmethod
    def _campos(data: dict) -> dict:
        return {
            "name": data.get("name"), "postal_codes": data.get("postal_codes"),
            "minimum_order": data.get("minimum_order"), "delivery_fee": data.get("delivery_fee"),
            "free_delivery_threshold": data.get("free_delivery_threshold"),
            "estimated_minutes": data.get("estimated_minutes"),
            "maximum_distance_km": data.get("maximum_distance_km"),
        }
