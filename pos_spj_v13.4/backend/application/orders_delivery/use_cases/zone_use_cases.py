"""Zonas de entrega (Configuración de Pedidos/Reparto, master prompt §21-22).

`DeliveryZone` y su repositorio existían, y `SetOrderDeliveryAddressUseCase` las
lee para resolver la zona y el costo de envío de un domicilio. Pero NADIE podía
crearlas: no había caso de uso ni pantalla, así que ningún pedido a domicilio
podía resolver su costo en la aplicación.

Las tres escrituras exigen `SETTINGS_MANAGE`, operan sólo sobre zonas de la
sucursal indicada (una zona de otra sucursal es "no existe") y no dejan dos zonas
activas compartiendo un código postal (`DeliveryZonePolicy.ensure_no_overlap`).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.domain.orders_delivery.exceptions import (
    DeliveryZoneNotFoundError,
    InvalidDeliveryZoneError,
    OrdersDeliveryDomainError,
)
from backend.domain.orders_delivery.policies.delivery_zone_policy import DeliveryZonePolicy
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


def _numero(valor, campo: str, *, opcional: bool = False) -> Decimal | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if opcional:
            return None
        raise InvalidDeliveryZoneError(f"{campo} es obligatorio")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation as exc:
        raise InvalidDeliveryZoneError(f"{campo} no es un número válido: {valor!r}") from exc
    if not numero.is_finite():
        raise InvalidDeliveryZoneError(f"{campo} no es un número válido: {valor!r}")
    return numero


def _minutos(valor) -> int | None:
    numero = _numero(valor, "El tiempo estimado", opcional=True)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise InvalidDeliveryZoneError("El tiempo estimado debe ser un número entero de minutos")
    return int(numero)


def _campos(*, name, postal_codes, minimum_order, delivery_fee, free_delivery_threshold,
            estimated_minutes, maximum_distance_km) -> dict:
    campos = dict(
        name=(name or "").strip(),
        postal_codes=DeliveryZonePolicy.normalize_postal_codes(postal_codes),
        minimum_order=_numero(minimum_order, "El pedido mínimo"),
        delivery_fee=_numero(delivery_fee, "El costo de envío"),
        free_delivery_threshold=_numero(free_delivery_threshold, "El envío gratis", opcional=True),
        estimated_minutes=_minutos(estimated_minutes),
        maximum_distance_km=_numero(maximum_distance_km, "La distancia máxima", opcional=True),
    )
    DeliveryZonePolicy.validate(**campos)
    return campos


def _zona_de_la_sucursal(uow, zone_id: str, branch_id: str) -> DeliveryZone:
    zona = uow.zones.get(zone_id)
    if zona is None or zona.branch_id != branch_id:
        raise DeliveryZoneNotFoundError(f"La zona {zone_id} no existe en esta sucursal")
    return zona


def _otras_activas(uow, zona: DeliveryZone) -> list[DeliveryZone]:
    return [z for z in uow.zones.list_active_for_branch(zona.branch_id) if z.id != zona.id]


class CreateDeliveryZoneUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, branch_id: str, name: str, postal_codes, minimum_order,
        delivery_fee, actor_user_id: str, operation_id: str, free_delivery_threshold=None,
        estimated_minutes=None, maximum_distance_km=None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTINGS_MANAGE)
            campos = _campos(
                name=name, postal_codes=postal_codes, minimum_order=minimum_order,
                delivery_fee=delivery_fee, free_delivery_threshold=free_delivery_threshold,
                estimated_minutes=estimated_minutes, maximum_distance_km=maximum_distance_km)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            try:
                zona = DeliveryZone.create(branch_id=branch_id, **campos)
                DeliveryZonePolicy.ensure_no_overlap(
                    zona, uow.zones.list_active_for_branch(branch_id))
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.zones.save(zona)
        return OrderResult.ok(
            "Zona de entrega creada", entity_id=zona.id, operation_id=operation_id)


class UpdateDeliveryZoneUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, zone_id: str, branch_id: str, name: str, postal_codes,
        minimum_order, delivery_fee, actor_user_id: str, operation_id: str,
        free_delivery_threshold=None, estimated_minutes=None, maximum_distance_km=None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTINGS_MANAGE)
            campos = _campos(
                name=name, postal_codes=postal_codes, minimum_order=minimum_order,
                delivery_fee=delivery_fee, free_delivery_threshold=free_delivery_threshold,
                estimated_minutes=estimated_minutes, maximum_distance_km=maximum_distance_km)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            try:
                zona = _zona_de_la_sucursal(uow, zone_id, branch_id)
                zona.update(**campos)
                # Una zona inactiva no resuelve domicilios: no puede chocar con nadie.
                if zona.active:
                    DeliveryZonePolicy.ensure_no_overlap(zona, _otras_activas(uow, zona))
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.zones.save(zona)
        return OrderResult.ok(
            "Zona de entrega actualizada", entity_id=zona.id, operation_id=operation_id)


class SetDeliveryZoneActiveUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, zone_id: str, branch_id: str, active: bool,
                actor_user_id: str, operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SETTINGS_MANAGE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            try:
                zona = _zona_de_la_sucursal(uow, zone_id, branch_id)
                if active:
                    # Mientras estuvo inactiva otra zona pudo tomar sus códigos.
                    DeliveryZonePolicy.ensure_no_overlap(zona, _otras_activas(uow, zona))
                    zona.activate()
                else:
                    zona.deactivate()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.zones.save(zona)
        return OrderResult.ok(
            "Zona de entrega activada" if active else "Zona de entrega desactivada",
            entity_id=zona.id, operation_id=operation_id)
