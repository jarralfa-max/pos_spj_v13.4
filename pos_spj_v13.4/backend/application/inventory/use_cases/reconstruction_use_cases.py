"""ReconstructBaseProductUseCase — the write side of reverse recipe
reconstruction (ERP integration master prompt §15-19, Fase 7).

`SellableAvailabilityQueryService` answers "how many could I reconstruct";
this is what actually does it: reserves the needed parts, posts TWO
canonical ledger movements — a `PRODUCTION_CONSUMPTION` consuming the parts and a
`PRODUCTION_OUTPUT` producing the assembled base product (hasta el 2026-09-19
eran ADJUSTMENT_OUT/IN), real component costs
summed onto it (never invented, §18) — and fulfills the reservations now
that the stock has genuinely moved. Two movements, one conceptual
operation, exactly as the master prompt's own §15 allows: `MovementType.
KIT_ASSEMBLY` exists and would be the natural single-movement fit, but it
maps to `MovementDirection.MIXED`, which `InventoryProjectionService`
explicitly does not implement yet (its own error: "VARIANCE/MIXED se
manejan en sus casos de uso específicos" — no such case exists). Extending
that shared, foundational projection service to support mixed-direction
movements is bigger and riskier than this feature's own scope — every
other movement type in the system depends on it too. Mirrors
`backend/infrastructure/integrations/sales_inventory_client.py`'s own
reserve -> post -> fulfill shape exactly, including composing the already-
canonical `CreateReservationUseCase`/`PostInventoryMovementUseCase`/
`FulfillReservationUseCase` on the SAME connection the same way that live,
production-proven client already does.

Traceability (§19): deliberately relies on the ledger itself rather than a
new mechanism — both movements share the same `operation_id` PREFIX and
`source_document_id`, and each consumed part's line carries its own
`lot_id` when the balance it was reserved from has one, so "which parts,
from which lots, made this reconstructed unit" is answerable by reading
those two movements together. (`ProcessGenealogyLink`, meat_processing's
own cross-order traceability table, was considered and deliberately NOT
reused here — it lives in meat_processing's own schema, and reaching into
it from Inventory would be a backwards cross-context dependency for a shop
that never uses meat_processing at all.)

Re-resolves eligibility and capacity itself at execution time — never
trusts a caller's stale availability read, since stock can move between a
check and an attempt to act on it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.reservation_use_cases import (
    CreateReservationUseCase,
    FulfillReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType, ReservationSource
from backend.domain.inventory.exceptions import InventoryConfigurationError
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.services.reverse_recipe_explosion_service import (
    ReverseRecipeExplosionService,
)
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)

logger = logging.getLogger("spj.inventory.reconstruction")


class ReconstructBaseProductUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy) -> None:
        # Obligatoria y sin valor por omisión (2026-09-19): ni permisiva
        # (`permissive_for_tests()` concedería todo) ni vacía por omisión (la
        # guarda `test_inventory_authorization_fail_closed` prohíbe ese patrón).
        # Quien olvide inyectarla recibe un error inmediato y claro.
        if authorization is None:
            raise InventoryConfigurationError(
                "ReconstructBaseProductUseCase requiere una política de autorización")
        self._auth = authorization
        self._explosion = ReverseRecipeExplosionService()

    def execute(
        self, connection, *, product_id: str, quantity, branch_id: str, warehouse_id: str,
        actor_user_id: str, operation_id: str,
        context: InventoryExecutionContext | None = None,
    ) -> InventoryResult:
        quantity = Decimal(str(quantity))
        if quantity <= 0:
            return InventoryResult.fail("La cantidad a reconstruir debe ser positiva",
                                        "INVALID_QUANTITY", operation_id=operation_id)

        # Fuente: el esquema de corte (decisión del usuario, Fase 7): el mismo
        # despiece que ejecuta Cárnico es el que se revierte.
        version = CuttingSchemeRepository(connection).reversible_active_version_for_input(
            product_id)
        if version is None:
            return InventoryResult.fail(
                "El producto no tiene un despiece reversible activo (§16)",
                "NOT_RECONSTRUCTIBLE", operation_id=operation_id)

        try:
            required = self._explosion.required_components_for(version, quantity)
        except ProductsDomainError as exc:
            return InventoryResult.fail(str(exc), "NOT_RECONSTRUCTIBLE",
                                        operation_id=operation_id)

        pricing = PricingReadFacade(connection)
        reservation_ids: list[str] = []
        consumption_lines: list[InventoryMovementLine] = []
        total_cost = Decimal("0")

        for component in required:
            unit_cost = pricing.unit_cost(component.component_product_id, branch_id)
            if unit_cost is None:
                self._release(connection, reservation_ids, actor_user_id=actor_user_id,
                              operation_id=operation_id)
                return InventoryResult.fail(
                    f"Sin costo configurado para {component.component_product_id}: "
                    "no se puede reconstruir con un costo inventado (§18)",
                    "MISSING_COMPONENT_COST", operation_id=operation_id)

            reserve_op = f"{operation_id}:reserve:{component.component_product_id}"
            reserved = CreateReservationUseCase(self._auth).execute(
                connection, product_id=component.component_product_id,
                branch_id=branch_id, warehouse_id=warehouse_id,
                location_id=branch_id, source=ReservationSource.RECONSTRUCTION,
                source_document_id=operation_id, quantity=component.quantity,
                operation_id=reserve_op, actor_user_id=actor_user_id, context=context)
            if not reserved.success:
                self._release(connection, reservation_ids, actor_user_id=actor_user_id,
                              operation_id=operation_id)
                return InventoryResult.fail(
                    f"No se pudo reservar {component.component_product_id}: {reserved.message}",
                    reserved.error_code or "INSUFFICIENT_AVAILABILITY",
                    operation_id=operation_id)
            reservation_ids.append(reserved.entity_id)

            component_cost = unit_cost * component.quantity
            total_cost += component_cost
            consumption_lines.append(InventoryMovementLine.create(
                product_id=component.component_product_id, quantity=component.quantity,
                from_location_id=branch_id, from_status=InventoryStatus.AVAILABLE,
                unit_cost=unit_cost, reason_code="RECONSTRUCTION"))

        unit_cost_of_reconstructed = (total_cost / quantity) if quantity else Decimal("0")

        # Two movements, one conceptual operation (the master prompt itself
        # allows this — §15's own note on compound transactions): the ledger
        # has no generic support for a mixed-direction single movement today
        # (KIT_ASSEMBLY maps to MovementDirection.MIXED, which
        # InventoryProjectionService explicitly does not implement yet — "sus
        # casos de uso específicos" don't exist). Both movements share the
        # same operation_id PREFIX, so reading the ledger for either finds
        # the other; a retry after only the first commits is safe — the
        # first's own operation_id dedups, the second is attempted again.
        # Transformación, no ajuste (Fase 7, 2026-09-19): con ADJUSTMENT_* cada
        # pollo armado aparecía en los reportes de ajustes/merma como si
        # alguien hubiera corregido existencias a mano.
        consumption = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_CONSUMPTION, branch_id=branch_id,
            warehouse_id=warehouse_id, source_module="inventory",
            source_document_type="RECONSTRUCTION", source_document_id=operation_id,
            operation_id=f"{operation_id}:consume", created_by_user_id=actor_user_id,
            lines=consumption_lines)
        # Permiso: el de RESERVAR, no el de movimientos manuales (Fase 7). El
        # armado sólo ocurre dentro de una venta y sobre un despiece que alguien
        # con permiso de despiece aprobó y marcó; exigir al cajero
        # `movimiento.crear_manual` hacía que un pollo armable terminara
        # pidiendo autorización de "sin existencia".
        consumed = PostInventoryMovementUseCase(self._auth).execute(
            connection, consumption, actor_user_id=actor_user_id, context=context,
            permission_code=InventoryPermissions.RESERVATION_CREATE)
        if not consumed.success:
            # Nunca se sigue adelante con un consumo fallido: cumplir las
            # reservas soltaría la retención de mercancía que sigue contada.
            self._release(connection, reservation_ids, actor_user_id=actor_user_id,
                          operation_id=operation_id)
            return InventoryResult.fail(
                consumed.message or "No se pudo postear el consumo de componentes.",
                consumed.error_code or "MOVEMENT_FAILED", operation_id=operation_id)

        production = InventoryMovement.create(
            movement_type=MovementType.PRODUCTION_OUTPUT, branch_id=branch_id,
            warehouse_id=warehouse_id, source_module="inventory",
            source_document_type="RECONSTRUCTION", source_document_id=operation_id,
            operation_id=f"{operation_id}:produce", created_by_user_id=actor_user_id,
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=quantity,
                to_location_id=branch_id, to_status=InventoryStatus.AVAILABLE,
                unit_cost=unit_cost_of_reconstructed, reason_code="RECONSTRUCTION")])
        posted = PostInventoryMovementUseCase(self._auth).execute(
            connection, production, actor_user_id=actor_user_id, context=context,
            permission_code=InventoryPermissions.RESERVATION_CREATE)
        if not posted.success:
            # The components are ALREADY consumed (real, committed stock
            # movement) — there is nothing to roll back here without a
            # proper reversal, and inventing one risks compounding the
            # failure. Surface it loudly; a retry with the same
            # operation_id will skip the already-posted consumption and
            # only retry this step.
            logger.error(
                "reconstruction %s: components consumed but production movement "
                "failed: %s", operation_id, posted.message)
            return InventoryResult.fail(
                posted.message or "No se pudo postear la producción reconstruida.",
                posted.error_code or "MOVEMENT_FAILED", operation_id=operation_id)

        self._project_cost(connection, product_id=product_id, quantity=quantity,
                           unit_cost=unit_cost_of_reconstructed,
                           operation_id=f"{operation_id}:produce",
                           actor_user_id=actor_user_id)

        for idx, reservation_id in enumerate(reservation_ids):
            fulfilled = FulfillReservationUseCase(self._auth).execute(
                connection, reservation_id=reservation_id,
                operation_id=f"{operation_id}:fulfill:{idx}",
                actor_user_id=actor_user_id, context=context)
            if not fulfilled.success:
                # El movimiento YA se posteó (mercancía ya se movió de verdad);
                # una reserva que no suelta aquí es un defecto de limpieza, no
                # una razón para revertir el ensamblaje ya real.
                logger.error(
                    "reconstruction %s: reservation %s posted but not fulfilled: %s",
                    operation_id, reservation_id, fulfilled.message)

        return InventoryResult.ok(
            "Reconstrucción completada", entity_id=posted.entity_id, operation_id=operation_id,
            product_id=product_id, quantity=str(quantity),
            unit_cost=str(unit_cost_of_reconstructed),
            cutting_scheme_version_id=version.id,
            consumption_movement_id=consumed.entity_id,
            already_processed=bool(posted.data.get("already_processed")),
            component_count=len(required))

    @staticmethod
    def _project_cost(connection, *, product_id, quantity, unit_cost, operation_id,
                      actor_user_id) -> None:
        """El costo de lo armado entra al costo PROMEDIO del producto.

        Antes el pollo reconstruido entraba al libro con el costo de sus partes
        pero `product_cost` no se enteraba, y el costo de venta (Fase 6) lo lee
        de ahí: un producto que sólo se arma nunca tenía costo, y uno que
        también se compra se vendía al costo de compra. Se usa el mismo
        contrato con que Producción informa lo que produce
        (`PRODUCTION_OUTPUT_COSTED` → `ProductCostProjectionHandler`), de forma
        síncrona: el bus de inventario no se despacha. Idempotente por
        `operation_id`. Un fallo aquí no deshace la reconstrucción ya asentada:
        se registra y el costo queda como estaba.
        """
        from backend.application.pricing.event_handlers.product_cost_projection_handler import (
            ProductCostProjectionHandler,
        )
        try:
            ProductCostProjectionHandler(connection).handle({
                "event_id": operation_id, "operation_id": operation_id,
                "user_id": actor_user_id,
                "lines": [{"product_id": product_id, "quantity": str(quantity),
                           "unit_cost": str(unit_cost)}]})
        except Exception:
            logger.exception("reconstrucción %s: no se actualizó el costo promedio de %s",
                             operation_id, product_id)

    def _release(self, connection, reservation_ids: list[str], *,
                actor_user_id: str, operation_id: str) -> None:
        """A partial reconstruction attempt (one component insufficient, or
        the assembly movement failed) must not leave earlier components in
        this attempt sitting reserved forever."""
        release_uc = ReleaseReservationUseCase(self._auth)
        for idx, reservation_id in enumerate(reservation_ids):
            result = release_uc.execute(
                connection, reservation_id=reservation_id,
                operation_id=f"{operation_id}:release:{idx}",
                actor_user_id=actor_user_id, reason="reconstrucción incompleta")
            if not result.success:
                logger.error("reconstruction %s: failed to release reservation %s: %s",
                            operation_id, reservation_id, result.message)
