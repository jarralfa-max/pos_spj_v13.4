"""Route use cases (master prompt §35): create, add stop, plan. Reuses
`ROUTE_PLAN` (ORD-1) for all three — assigning a route to a driver/activating
it are ORD-18's concern (dispatch), reusing the `DeliveryRoute.assign_driver()/
activate()/complete()/cancel()` methods already built here.
"""

from __future__ import annotations

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.exceptions import (
    DeliveryJobNotFoundError,
    OrdersDeliveryDomainError,
    RouteNotFoundError,
)
from backend.domain.orders_delivery.route import DeliveryRoute
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class CreateRouteUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, branch_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ROUTE_PLAN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            route = DeliveryRoute.create(branch_id=branch_id)
            uow.routes.save(route)
        return OrderResult.ok("Ruta creada", entity_id=route.id, operation_id=operation_id)


class AddStopToRouteUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, route_id: str, delivery_job_id: str, sequence: int,
        actor_user_id: str, operation_id: str, estimated_arrival_at: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ROUTE_PLAN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            route = uow.routes.get(route_id)
            if route is None:
                return fail_from_domain_error(
                    RouteNotFoundError(f"Ruta {route_id} no existe"), operation_id=operation_id)
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                route.add_stop(delivery_job_id=delivery_job_id, sequence=sequence,
                                estimated_arrival_at=estimated_arrival_at)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            job.route_id = route.id
            uow.routes.save(route)
            uow.delivery_jobs.save(job)
        return OrderResult.ok(
            "Parada agregada a la ruta", entity_id=route.id, operation_id=operation_id,
            stop_count=len(route.stops))


class PlanRouteUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, route_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ROUTE_PLAN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            route = uow.routes.get(route_id)
            if route is None:
                return fail_from_domain_error(
                    RouteNotFoundError(f"Ruta {route_id} no existe"), operation_id=operation_id)
            try:
                route.plan()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.routes.save(route)
        return OrderResult.ok("Ruta planificada", entity_id=route.id, operation_id=operation_id)
