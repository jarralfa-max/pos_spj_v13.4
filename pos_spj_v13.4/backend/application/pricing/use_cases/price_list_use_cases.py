"""Ciclo de vida de una lista de precios: crear → enviar → aprobar → activar →
desactivar.

Las transiciones las decide la ENTIDAD (`PriceList._transition`), no estos casos
de uso: aquí sólo se valida permiso, segregación de funciones y se persiste. Una
lista APROBADA o ACTIVA es inmutable por regla de dominio; para cambiarla se crea
otra.

Transaccionalidad: este contexto no tiene UnitOfWork —el repositorio declara que
nunca hace commit y el proyector de costos gestiona la suya— así que cada caso de
uso confirma o revierte explícitamente.
"""

from __future__ import annotations

import json
import logging

from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.pricing.permissions import PricingPermissions
from backend.application.pricing.result import PricingResult
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.events import PricingEvents, build_pricing_event_payload
from backend.domain.pricing.exceptions import (
    PricingDomainError,
    PricingPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)

logger = logging.getLogger("spj.pricing.price_list_use_cases")


class _BasePriceListUseCase:
    def __init__(self, authorization: PricingAuthorizationPolicy | None = None) -> None:
        # Mismo contrato que el resto del ERP: sin checker la política permite
        # (pruebas aisladas); la composición viva siempre inyecta uno.
        self._auth = authorization or PricingAuthorizationPolicy()

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


class CreatePriceListUseCase(_BasePriceListUseCase):
    """Alta de una lista en BORRADOR.

    Registra al creador: sin ese dato `ensure_segregation` no tiene contra qué
    comparar y la regla "quien crea no aprueba" es decorativa.
    """

    def execute(self, connection, *, actor_user_id: str, code: str, name: str,
                kind: str, operation_id: str, channel: str | None = None,
                discount_pct: str = "0",
                inherits_from_id: str | None = None) -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.LIST_CREATE)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)
        try:
            price_list = PriceList(
                code=code, name=name, kind=PriceListKind(str(kind)), channel=channel,
                discount_pct=discount_pct, inherits_from_id=inherits_from_id,
                created_by_user_id=actor_user_id)
            price_list.ensure_channel_is_applicable()
        except (PricingDomainError, ValueError) as exc:
            return PricingResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        repo = PricingRepository(connection)
        try:
            repo.save_list(price_list)
            self._emit(repo, PricingEvents.PRICE_LIST_CREATED, entity_id=price_list.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       code=price_list.code, kind=price_list.kind.value)
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("No se pudo crear la lista de precios %s", code)
            raise
        return PricingResult.ok("Lista de precios creada", entity_id=price_list.id,
                                operation_id=operation_id, code=price_list.code)


class DuplicatePriceListUseCase(_BasePriceListUseCase):
    """Copia una lista a otra nueva en BORRADOR, con sus precios.

    POR QUÉ copia los precios y no sólo la cabecera: una lista APROBADA o ACTIVA
    es inmutable por regla de dominio, así que duplicar es la ÚNICA forma de
    partir de una lista vigente para cambiarla. Una copia sin precios no sirve
    para eso — sería una lista nueva con otro nombre.

    NO introduce vocabulario de dominio nuevo. Una lista se crea de verdad
    (`PRICE_LIST_CREATED`, con `duplicated_from` en la carga útil) y cada precio
    copiado es un cambio de precio real (`PRODUCT_PRICE_CHANGED`). Un
    `PRICE_LIST_DUPLICATED` sería nombrar por segunda vez lo que ya está
    nombrado, y `build_pricing_event_payload` rechaza los nombres no
    registrados, así que tampoco podría colarse sin declararlo.

    El creador de la copia es quien duplica, NO el de la original: heredarlo
    dejaría que quien duplica aprobara su propia lista, y la segregación de
    funciones —que en este contexto ya estuvo rota una vez por no persistir al
    creador— volvería a ser decorativa.
    """

    def execute(self, connection, *, actor_user_id: str, source_list_id: str,
                code: str, name: str, operation_id: str,
                copy_prices: bool = True) -> PricingResult:
        try:
            self._auth.require(actor_user_id, PricingPermissions.LIST_CREATE)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)

        repo = PricingRepository(connection)
        origen = repo.get_list(source_list_id)
        if origen is None:
            return PricingResult.fail("La lista de origen no existe", "NOT_FOUND",
                                      operation_id=operation_id)
        try:
            copia = PriceList(
                code=code, name=name, kind=origen.kind, channel=origen.channel,
                discount_pct=str(origen.discount_pct),
                inherits_from_id=origen.inherits_from_id,
                created_by_user_id=actor_user_id)
        except (PricingDomainError, ValueError) as exc:
            return PricingResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        copiados = 0
        try:
            repo.save_list(copia)
            self._emit(repo, PricingEvents.PRICE_LIST_CREATED, entity_id=copia.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       code=copia.code, kind=copia.kind.value,
                       duplicated_from=origen.id)
            if copy_prices:
                for precio in repo.prices_of_list(source_list_id):
                    nuevo = ProductPrice(
                        price_list_id=copia.id, product_id=precio.product_id,
                        sale_price=precio.sale_price, branch_id=precio.branch_id,
                        min_price=precio.min_price,
                        effective_from=precio.effective_from,
                        effective_to=precio.effective_to)
                    repo.save_price(nuevo)
                    self._emit(repo, PricingEvents.PRODUCT_PRICE_CHANGED,
                               entity_id=nuevo.id, operation_id=operation_id,
                               user_id=actor_user_id, product_id=nuevo.product_id,
                               branch_id=nuevo.branch_id,
                               sale_price=str(nuevo.sale_price.amount),
                               currency=nuevo.sale_price.currency)
                    copiados += 1
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("No se pudo duplicar la lista %s", source_list_id)
            raise
        return PricingResult.ok(
            f"Lista duplicada con {copiados} precio(s)", entity_id=copia.id,
            operation_id=operation_id, copied_prices=copiados)


class _TransitionUseCase(_BasePriceListUseCase):
    """Transición de estado sobre una lista existente."""

    permission: str = ""
    event_name: str = ""
    #: Cuando es True se exige que el actor NO sea quien creó la lista.
    segregated: bool = False
    success_message: str = "Operación registrada"

    def _apply(self, price_list: PriceList, *, actor_user_id: str) -> None:
        raise NotImplementedError

    def _side_effects(self, repo, price_list: PriceList, *, actor_user_id: str,
                      operation_id: str) -> None:
        """Cambios a OTRAS listas en la misma transacción (por omisión, ninguno)."""

    def execute(self, connection, *, actor_user_id: str, price_list_id: str,
                operation_id: str) -> PricingResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except PricingPermissionDeniedError as exc:
            return PricingResult.fail(str(exc), "PERMISSION_DENIED",
                                      operation_id=operation_id)

        repo = PricingRepository(connection)
        price_list = repo.get_list(price_list_id)
        if price_list is None:
            return PricingResult.fail("La lista de precios no existe", "NOT_FOUND",
                                      operation_id=operation_id)
        if self.segregated:
            try:
                self._auth.ensure_segregation(
                    actor_user_id=actor_user_id,
                    creator_user_id=price_list.created_by_user_id,
                    approval_permission=self.permission)
            except SegregationOfDutiesError as exc:
                return PricingResult.fail(str(exc), "SEGREGATION_OF_DUTIES",
                                          operation_id=operation_id)
        try:
            self._apply(price_list, actor_user_id=actor_user_id)
        except PricingDomainError as exc:
            return PricingResult.fail(str(exc), "INVALID_STATE",
                                      operation_id=operation_id)

        try:
            self._side_effects(repo, price_list, actor_user_id=actor_user_id,
                               operation_id=operation_id)
            repo.save_list(price_list)
            self._emit(repo, self.event_name, entity_id=price_list.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       status=price_list.status.value)
            connection.commit()
        except Exception:
            self._rollback(connection)
            logger.exception("Transición fallida en la lista %s", price_list_id)
            raise
        return PricingResult.ok(self.success_message, entity_id=price_list.id,
                                operation_id=operation_id,
                                status=price_list.status.value)


class SubmitPriceListUseCase(_TransitionUseCase):
    permission = PricingPermissions.LIST_SUBMIT
    event_name = PricingEvents.PRICE_LIST_SUBMITTED
    success_message = "Lista enviada a revisión"

    def _apply(self, price_list, *, actor_user_id):
        price_list.submit()


class ApprovePriceListUseCase(_TransitionUseCase):
    permission = PricingPermissions.LIST_APPROVE
    event_name = PricingEvents.PRICE_LIST_APPROVED
    segregated = True
    success_message = "Lista aprobada"

    def _apply(self, price_list, *, actor_user_id):
        price_list.approve(approved_by_user_id=actor_user_id)


class ActivatePriceListUseCase(_TransitionUseCase):
    permission = PricingPermissions.LIST_ACTIVATE
    event_name = PricingEvents.PRICE_LIST_ACTIVATED
    segregated = True
    success_message = "Lista activada"

    def _apply(self, price_list, *, actor_user_id):
        price_list.activate()

    def _side_effects(self, repo, price_list, *, actor_user_id, operation_id):
        """Siempre hay EXACTAMENTE una lista base (decisión del usuario,
        2026-09-30): activar otra la REEMPLAZA en la misma operación. Antes
        convivían dos activas y mandaba la de modificación más reciente, sin
        que nadie lo eligiera."""
        if price_list.kind is not PriceListKind.BASE:
            return
        for previous in repo.active_lists_of_kind(PriceListKind.BASE):
            if previous.id == price_list.id:
                continue
            previous.deactivate()
            repo.save_list(previous)
            self._emit(repo, PricingEvents.PRICE_LIST_DEACTIVATED, entity_id=previous.id,
                       operation_id=operation_id, user_id=actor_user_id,
                       status=previous.status.value, replaced_by=price_list.id)


class DeactivatePriceListUseCase(_TransitionUseCase):
    permission = PricingPermissions.LIST_DEACTIVATE
    event_name = PricingEvents.PRICE_LIST_DEACTIVATED
    success_message = "Lista desactivada"

    def _apply(self, price_list, *, actor_user_id):
        price_list.deactivate()
