"""Dirección de entrega para pruebas que llevan un pedido a domicilio por sus casos de uso.

Confirmar un pedido con entrega exige dirección (`OrderConfirmationPolicy`). Las
pruebas del flujo de despacho, reentrega y PWA confirmaban pedidos a domicilio sin
ella; este ayudante hace lo que hace la aplicación: una zona que cubre el código
postal y `SetOrderDeliveryAddressUseCase`.

La zona cobra $0 y no exige pedido mínimo, a propósito: esas pruebas afirman
totales y cobros, y el costo de envío no es lo que prueban.
"""
from __future__ import annotations

from backend.application.orders_delivery.use_cases.address_use_cases import (
    SetOrderDeliveryAddressUseCase,
)
from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.infrastructure.db.repositories.orders_delivery.delivery_zone_repository import (
    DeliveryZoneRepository,
)
from backend.shared.ids import new_uuid


def give_delivery_address(conn, order_id: str, *, branch_id: str, authorization,
                          actor_user_id: str | None = None) -> None:
    """`actor_user_id` importa con una política de sesión: el checker real sólo
    concede permisos al usuario de la sesión."""
    # Un código postal por llamada: dos zonas activas no pueden compartirlo.
    codigo_postal = f"CP{new_uuid()[-8:]}"
    DeliveryZoneRepository(conn).save(DeliveryZone.create(
        branch_id=branch_id, name=f"Zona {codigo_postal}", postal_codes=(codigo_postal,)))
    conn.commit()
    resultado = SetOrderDeliveryAddressUseCase(authorization).execute(
        conn, order_id=order_id, recipient_name="Ana", recipient_phone="5555555555",
        street="Reforma", exterior_number="100", postal_code=codigo_postal,
        actor_user_id=actor_user_id or new_uuid(), operation_id=new_uuid())
    assert resultado.success, resultado.message
