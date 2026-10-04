"""Cumpleaños del cliente (decisión del usuario, 2026-10-03): opcional y con
consentimiento. Sin consentimiento NO se guarda; retirarlo borra el dato.
Lo usa Fidelidad (bono de cumpleaños en reglas y beneficio de cumpleaños)."""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.value_objects.birthday import CustomerBirthday
from backend.infrastructure.db.repositories.customers.birthday_repository import (
    CustomerBirthdayRepository,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class SetCustomerBirthdayUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
                month: int | None = None, day: int | None = None, year: int | None = None,
                consent: bool = False) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if uow.customers.get(customer_id) is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            repo = CustomerBirthdayRepository(uow.connection)
            if not consent or not month or not day:
                if repo.get(customer_id) is not None:
                    repo.delete(customer_id)
                    uow.audit.record(action="CUSTOMER_BIRTHDAY_REMOVED",
                                     actor_user_id=actor_user_id, customer_id=customer_id,
                                     reason="sin consentimiento", operation_id=operation_id)
                if (month or day) and not consent:
                    return CustomerResult.fail(
                        "Para guardar el cumpleaños el cliente debe autorizarlo "
                        "(consentimiento).", "CONSENT_REQUIRED", operation_id=operation_id)
                return CustomerResult.ok("Cumpleaños sin registrar", entity_id=customer_id,
                                         operation_id=operation_id)
            try:
                cumple = CustomerBirthday(int(month), int(day), int(year) if year else None)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            repo.save(customer_id, cumple, actor_user_id=actor_user_id)
            uow.audit.record(action="CUSTOMER_BIRTHDAY_SET", actor_user_id=actor_user_id,
                             customer_id=customer_id, reason="con consentimiento",
                             operation_id=operation_id)
        return CustomerResult.ok("Cumpleaños guardado", entity_id=customer_id,
                                 operation_id=operation_id)


def customer_birthday(connection, customer_id: str) -> CustomerBirthday | None:
    return CustomerBirthdayRepository(connection).get(customer_id)


__all__ = ["SetCustomerBirthdayUseCase", "customer_birthday"]
