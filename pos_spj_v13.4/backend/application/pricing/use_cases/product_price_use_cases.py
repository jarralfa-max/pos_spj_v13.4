"""Fijar el precio de venta de un producto y sus escalas por volumen.

Tres reglas que NO se reimplementan aquí porque ya viven en el dominio:

* `ProductPrice` rechaza construirse con un precio de venta por debajo de su
  propio mínimo, así que ese camino no se puede saltar por accidente.
* `MarginPolicy.allows()` decide si un precio respeta el mínimo del producto;
  vender por debajo exige autorización EN CALIENTE de otro usuario con
  `PricingPermissions.PRICE_MIN_OVERRIDE`, y eso lo resuelve
  `PricingAuthorizationPolicy.authorize_exception`.
* La vigencia (`effective_from` / `effective_to`) es parte de la entidad: no
  hace falta una tabla aparte para "programar" un precio.

Alcance por sucursal: `allowed_branches` se INYECTA (None = alcance global, que
es el contrato que la propia política documenta). No se resuelve aquí porque el
ERP todavía no tiene un resolutor de sucursales permitidas por usuario — cuando
lo tenga, se conecta sin tocar este caso de uso.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.pricing.permissions import PricingPermissions
from backend.application.pricing.result import PricingResult
from backend.application.products.queries.product_selection_query_service import (
    ProductSearchQuery,
)
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.events import PricingEvents, build_pricing_event_payload
from backend.domain.pricing.exceptions import (
    BranchScopeError,
    PricingDomainError,
    PricingPermissionDeniedError,
)
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)

logger = logging.getLogger("spj.pricing.product_price_use_cases")


def _money(amount, currency: str) -> Money:
    """Decimal-only: un `float` aquí sería un error de redondeo silencioso en
    dinero, y `Money` lo rechaza por diseño."""
    return Money(Decimal(str(amount)), currency)


class _BasePriceUseCase:
    def __init__(self, authorization: PricingAuthorizationPolicy | None = None,
                 authorizer_authorization: PricingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PricingAuthorizationPolicy()
        #: Sólo para `authorize_exception`. Ver la nota de
        #: `SetProductPriceUseCase`: el autorizador no es el usuario de la
        #: sesión, así que no puede validarse con el mismo verificador.
        self._authorizer_auth = authorizer_authorization or self._auth

    @staticmethod
    def _emit(repo: PricingRepository, event_name: str, *, entity_id: str,
              operation_id: str, user_id: str | None, **extra) -> None:
        payload = build_pricing_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            user_id=user_id, **extra)
        repo.enqueue_event(event_id=payload["event_id"], event_name=event_name,
                           operation_id=operation_id, entity_id=entity_id,
                           payload=json.dumps(payload))

    @staticmethod
    def _rollback(connection) -> None:
        rollback = getattr(connection, "rollback", None)
        if rollback is not None:
            rollback()


class SetProductPriceUseCase(_BasePriceUseCase):
    """Alta o cambio del precio de venta de un producto en una lista.

    `authorizer_authorization` es una política SEPARADA, usada sólo para
    validar al AUTORIZADOR de una excepción. Hace falta porque el verificador
    de sesión sólo concede al usuario de la sesión, y el autorizador es por
    definición otra persona: con un único verificador, autorizar bajo el mínimo
    se denegaba siempre. Si no se inyecta, se usa la política normal — que es
    el comportamiento anterior, y deniega.

    `authorized_by` + `authorization_reason` sólo hacen falta para fijar un
    precio por debajo del mínimo: producen un `PricingAuthorizationGrant` real
    (autorizador distinto del solicitante y con el permiso de excepción) y
    quedan registrados en la bitácora de cambios.

    La composición viva inyecta como `authorizer_authorization` una política
    respaldada por `AuthorizerPermissionChecker`, que resuelve permisos
    de cualquier usuario contra `rol_permisos`. Sin esa inyección este camino
    deniega siempre —el verificador de sesión no puede validar a nadie más que
    al usuario de la sesión— y denegar es lo correcto: es preferible a
    aparentar que la excepción se concedió.
    """

    def execute(self, connection, *, actor_user_id: str, price_list_id: str,
                product_id: str, sale_price, operation_id: str,
                branch_id: str | None = None, currency: str = "MXN",
                min_price=None, effective_from: str | None = None,
                effective_to: str | None = None,
                allowed_branches=None, authorized_by: str | None = None,
                authorization_reason: str = "") -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.PRICE_EDIT)
            self._auth.require_branch(actor_user_id, branch_id,
                                      allowed_branches=allowed_branches)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)
        except BranchScopeError as exc:
            return PricingResult.fail(str(exc), "BRANCH_SCOPE",
                                      operation_id=operation_id)

        repo = PricingRepository(connection)
        price_list = repo.get_list(price_list_id)
        if price_list is None:
            return PricingResult.fail("La lista de precios no existe", "NOT_FOUND",
                                      operation_id=operation_id)
        if not price_list.is_editable:
            return PricingResult.fail(
                f"La lista está {price_list.status.value} y es inmutable: "
                "crea una nueva para cambiar precios",
                "IMMUTABLE_LIST", operation_id=operation_id)

        anterior = repo.get_price(price_list_id=price_list_id, product_id=product_id,
                                  branch_id=branch_id)
        grant = None
        try:
            nuevo = _money(sale_price, currency)
            minimo = _money(min_price, currency) if min_price is not None else None
            # Precio bajo el mínimo: sólo con autorización en caliente de OTRO
            # usuario. Sin ella, la propia entidad rechaza construirse.
            if minimo is not None and nuevo < minimo:
                if not authorized_by:
                    return PricingResult.fail(
                        "El precio es menor al mínimo: requiere autorización",
                        "BELOW_MINIMUM", operation_id=operation_id)
                grant = self._authorizer_auth.authorize_exception(
                    authorizer_user_id=authorized_by, requested_by=actor_user_id,
                    permission_code=PricingPermissions.PRICE_MIN_OVERRIDE,
                    operation_id=operation_id, reason=authorization_reason,
                    entity_id=product_id)
                minimo = None  # autorizado: no se impone el mínimo a la entidad
            precio = ProductPrice(
                price_list_id=price_list_id, product_id=product_id,
                sale_price=nuevo, branch_id=branch_id, min_price=minimo,
                effective_from=effective_from, effective_to=effective_to)
            if anterior is not None:
                precio.id = anterior.id
        except PricingDomainError as exc:
            return PricingResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        try:
            repo.save_price(precio)
            repo.log_price_change(
                product_id=product_id, branch_id=branch_id, field="sale_price",
                old_value=anterior.sale_price if anterior else None,
                new_value=nuevo, operation_id=operation_id, user_id=actor_user_id,
                authorized_by=grant.authorized_by if grant else None,
                reason=authorization_reason or None)
            self._emit(repo, PricingEvents.PRODUCT_PRICE_CHANGED, entity_id=precio.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       product_id=product_id, branch_id=branch_id,
                       sale_price=str(nuevo.amount), currency=nuevo.currency)
            if grant is not None:
                self._emit(repo, PricingEvents.PRICE_BELOW_MINIMUM_AUTHORIZED,
                           entity_id=precio.id, operation_id=operation_id,
                           user_id=actor_user_id, product_id=product_id,
                           authorized_by=grant.authorized_by)
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("No se pudo fijar el precio de %s", product_id)
            raise
        return PricingResult.ok("Precio actualizado", entity_id=precio.id,
                                operation_id=operation_id,
                                sale_price=str(nuevo.amount))


class ApplyPriceToSelectionUseCase(_BasePriceUseCase):
    """Aplica UN precio a MUCHOS productos en una sola operación.

    La selección se resuelve con el contrato compartido `ProductSearchQuery`, no
    con una consulta propia: una segunda forma de filtrar el catálogo dentro de
    Precios sería exactamente la "versión por módulo" de la búsqueda que el
    contrato compartido existe para impedir. Precios sólo añade restricciones
    (activo + categoría), como cualquier otro consumidor.

    `BRANCH_PRICE_MANAGE` estaba en el vocabulario y no lo exigía ningún caso de
    uso. Fijar el precio de UNA sucursal es una facultad distinta de fijar el
    precio general, y en un lote es donde más pesa, porque cambia muchos precios
    de golpe. Por eso aquí se exige, además de `PRICE_EDIT`.

    NO acepta precio bajo mínimo. La autorización en caliente es cara —un
    gerente autorizando delante del terminal— y concederla una vez para un lote
    entero convertiría una excepción puntual en una barra libre. Un precio bajo
    el mínimo se fija producto por producto.
    """

    def __init__(self, authorization: PricingAuthorizationPolicy | None = None,
                 product_search_factory=None) -> None:
        super().__init__(authorization)
        #: Puerto estructural hacia la búsqueda compartida de Productos. Sin él
        #: la selección por categoría no se puede resolver y la operación falla
        #: con EMPTY_SELECTION en vez de aplicar el precio a nada.
        self._product_search = product_search_factory

    def _products_in_category(self, category_id: str, max_products: int) -> list[str]:
        if self._product_search is None:
            return []
        try:
            dtos = self._product_search().search(ProductSearchQuery(
                category_id=str(category_id), active_only=True,
                page_size=int(max_products)))
        except Exception:
            logger.exception("No se pudieron resolver los productos de la categoría %s",
                             category_id)
            return []
        return [d.product_id for d in dtos]

    def execute(self, connection, *, actor_user_id: str, price_list_id: str,
                sale_price, operation_id: str, category_id: str | None = None,
                product_ids=None, branch_id: str | None = None,
                currency: str = "MXN", min_price=None,
                max_products: int = 500) -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.PRICE_EDIT)
            if branch_id:
                self._auth.require(actor_user_id,
                                   PricingPermissions.BRANCH_PRICE_MANAGE)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)

        objetivo = [str(p) for p in (product_ids or []) if str(p).strip()]
        if not objetivo and category_id:
            objetivo = self._products_in_category(category_id, max_products)
        if not objetivo:
            return PricingResult.fail(
                "La selección no tiene productos: elige una categoría con "
                "productos activos.", "EMPTY_SELECTION", operation_id=operation_id)

        repo = PricingRepository(connection)
        price_list = repo.get_list(price_list_id)
        if price_list is None:
            return PricingResult.fail("La lista de precios no existe", "NOT_FOUND",
                                      operation_id=operation_id)
        if not price_list.is_editable:
            return PricingResult.fail(
                f"La lista está {price_list.status.value} y es inmutable: "
                "duplícala para cambiar precios",
                "IMMUTABLE_LIST", operation_id=operation_id)

        try:
            nuevo = _money(sale_price, currency)
            minimo = _money(min_price, currency) if min_price is not None else None
        except PricingDomainError as exc:
            return PricingResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        if minimo is not None and nuevo < minimo:
            return PricingResult.fail(
                "El precio es menor al mínimo: en lote no se autoriza, "
                "fíjalo producto por producto.",
                "BELOW_MINIMUM", operation_id=operation_id)

        aplicados, rechazados = 0, 0
        try:
            for product_id in objetivo:
                anterior = repo.get_price(price_list_id=price_list_id,
                                          product_id=product_id, branch_id=branch_id)
                try:
                    precio = ProductPrice(
                        price_list_id=price_list_id, product_id=product_id,
                        sale_price=nuevo, branch_id=branch_id, min_price=minimo)
                except PricingDomainError:
                    # Un producto que el dominio rechaza no aborta el lote, pero
                    # tampoco se cuenta: el resultado dice cuántos se aplicaron y
                    # cuántos se rechazaron, para que no parezca completo.
                    rechazados += 1
                    continue
                if anterior is not None:
                    precio.id = anterior.id
                repo.save_price(precio)
                repo.log_price_change(
                    product_id=product_id, branch_id=branch_id, field="sale_price",
                    old_value=anterior.sale_price if anterior else None,
                    new_value=nuevo, operation_id=operation_id,
                    user_id=actor_user_id, authorized_by=None, reason=None)
                self._emit(repo, PricingEvents.PRODUCT_PRICE_CHANGED,
                           entity_id=precio.id, operation_id=operation_id,
                           user_id=actor_user_id, product_id=product_id,
                           branch_id=branch_id, sale_price=str(nuevo.amount),
                           currency=nuevo.currency)
                aplicados += 1
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("No se pudo aplicar el precio en lote")
            raise

        mensaje = f"Precio aplicado a {aplicados} producto(s)"
        if rechazados:
            mensaje += f"; {rechazados} rechazado(s) por el dominio"
        return PricingResult.ok(mensaje, operation_id=operation_id,
                                applied=aplicados, rejected=rechazados,
                                selected=len(objetivo))


class SetVolumePriceUseCase(_BasePriceUseCase):
    """Escala por volumen sobre un precio existente (kg ≥ N → precio especial)."""

    def execute(self, connection, *, actor_user_id: str, product_price_id: str,
                min_quantity, price, operation_id: str,
                currency: str = "MXN") -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.VOLUME_PRICE_MANAGE)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)
        try:
            escala = VolumePrice(product_price_id=product_price_id,
                                 min_quantity=Decimal(str(min_quantity)),
                                 price=_money(price, currency))
        except PricingDomainError as exc:
            return PricingResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        repo = PricingRepository(connection)
        try:
            repo.save_volume(escala)
            self._emit(repo, PricingEvents.VOLUME_PRICE_CHANGED, entity_id=escala.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       min_quantity=str(escala.min_quantity),
                       price=str(escala.price.amount))
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("No se pudo fijar la escala por volumen de %s",
                             product_price_id)
            raise
        return PricingResult.ok("Escala por volumen registrada", entity_id=escala.id,
                                operation_id=operation_id)
