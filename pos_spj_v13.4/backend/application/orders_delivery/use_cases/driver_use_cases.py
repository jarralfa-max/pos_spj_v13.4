"""Driver profile and assignment use cases (master prompt §33-34).

`AcceptAssignmentUseCase`/`RejectAssignmentUseCase` record the DRIVER's own
decision — no self-service driver PWA exists yet (ORD-25), so staff records
it on the driver's behalf for now, same "no self-service channel yet"
reasoning already applied to customer approval (ORD-10/11) and pickup
notification (ORD-14).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.driver import DeliveryAssignment, DriverOperationalProfile
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import (
    AssignmentNotFoundError,
    DriverProfileNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.domain.orders_delivery.policies.driver_assignment_policy import DriverAssignmentPolicy
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class RegisterDriverProfileUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, driver_id: str, branch_id: str, actor_user_id: str,
        operation_id: str, vehicle_type: str | None = None, capacity: int = 1,
        cash_limit: Decimal = Decimal("0"),
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DRIVER_STATUS_MANAGE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            existing = uow.driver_profiles.get_by_driver_id(driver_id)
            if existing is not None:
                return OrderResult.ok(
                    "Perfil de repartidor ya existente (idempotente)", entity_id=existing.id,
                    operation_id=operation_id)
            try:
                profile = DriverOperationalProfile.create(
                    driver_id=driver_id, branch_id=branch_id, vehicle_type=vehicle_type,
                    capacity=capacity, cash_limit=cash_limit)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.driver_profiles.save(profile)
        return OrderResult.ok(
            "Perfil de repartidor registrado", entity_id=profile.id, operation_id=operation_id)


class ProposeAssignmentUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, delivery_job_id: str, driver_id: str, actor_user_id: str,
        operation_id: str, vehicle_id: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DRIVER_ASSIGN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            profile = uow.driver_profiles.get_by_driver_id(driver_id)
            if profile is None:
                return fail_from_domain_error(
                    DriverProfileNotFoundError(f"Repartidor {driver_id} sin perfil operativo"),
                    operation_id=operation_id)
            try:
                DriverAssignmentPolicy.ensure_can_assign(profile)
                assignment = DeliveryAssignment.create(
                    delivery_job_id=delivery_job_id, driver_id=driver_id,
                    assigned_by_user_id=actor_user_id, vehicle_id=vehicle_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            profile.increment_assignments()
            uow.driver_profiles.save(profile)
            uow.assignments.save(assignment)
        return OrderResult.ok(
            "Asignación propuesta", entity_id=assignment.id, operation_id=operation_id)


class AcceptAssignmentUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, assignment_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DRIVER_STATUS_MANAGE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            assignment = uow.assignments.get(assignment_id)
            if assignment is None:
                return fail_from_domain_error(
                    AssignmentNotFoundError(f"Asignación {assignment_id} no existe"),
                    operation_id=operation_id)
            job = uow.delivery_jobs.get(assignment.delivery_job_id)
            try:
                assignment.accept()
                if job is not None:
                    job.assign_driver(driver_id=assignment.driver_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.assignments.save(assignment)
            if job is not None:
                uow.delivery_jobs.save(job)
                self._emit_delivery(
                    uow, DeliveryEvents.DRIVER_ASSIGNED, entity_id=job.id,
                    operation_id=operation_id, branch_id=job.branch_id,
                    actor_user_id=actor_user_id, driver_id=assignment.driver_id)
        return OrderResult.ok(
            "Asignación aceptada por el repartidor", entity_id=assignment.id,
            operation_id=operation_id)


class RejectAssignmentUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, assignment_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DRIVER_STATUS_MANAGE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            assignment = uow.assignments.get(assignment_id)
            if assignment is None:
                return fail_from_domain_error(
                    AssignmentNotFoundError(f"Asignación {assignment_id} no existe"),
                    operation_id=operation_id)
            profile = uow.driver_profiles.get_by_driver_id(assignment.driver_id)
            try:
                assignment.reject()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            if profile is not None:
                profile.decrement_assignments()
                uow.driver_profiles.save(profile)
            uow.assignments.save(assignment)
        return OrderResult.ok(
            "Asignación rechazada por el repartidor", entity_id=assignment.id,
            operation_id=operation_id)
