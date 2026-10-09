"""Cuentas comerciales del cliente (§13, CRM-43): alta y edición.

``CustomerAccount`` existía (dominio, tabla, repositorio) pero sólo nacía al
convertir un prospecto con empresa: no había forma de registrar la cuenta de
un cliente empresarial ya existente ni de corregir su giro, tamaño o sitio.

Permiso: ``CLIENTES.editar`` (la cuenta es parte del expediente). Audita y
publica ``CUSTOMER_UPDATED`` como cualquier cambio del maestro.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

ACCOUNT_TYPES = ("BUSINESS", "WHOLESALE", "INSTITUTIONAL", "RESTAURANT", "RETAIL", "OTHER")
COMPANY_SIZES = ("MICRO", "SMALL", "MEDIUM", "LARGE")


class _Base:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _deny(self, actor_user_id: str, operation_id: str) -> CustomerResult | None:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        return None

    @staticmethod
    def _record(uow, actor_user_id: str, account: CustomerAccount, reason: str,
                operation_id: str) -> None:
        uow.audit.record(action=CustomerEvents.UPDATED, actor_user_id=actor_user_id,
                         customer_id=account.customer_id, after_json=json.dumps({
                             "account_id": account.id, "account_type": account.account_type,
                             "industry": account.industry, "company_size": account.company_size,
                             "website": account.website, "status": account.status}),
                         reason=reason, operation_id=operation_id)
        payload = build_event_payload(CustomerEvents.UPDATED, operation_id=operation_id,
                                      customer_id=account.customer_id, user_id=actor_user_id,
                                      account_id=account.id)
        uow.outbox.enqueue(payload["event_id"], CustomerEvents.UPDATED, json.dumps(payload),
                           operation_id)


class CreateCustomerAccountUseCase(_Base):
    def execute(self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
                account_type: str = "BUSINESS", industry: str = "", company_size: str = "",
                website: str = "", parent_account_id: str | None = None) -> CustomerResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        if account_type not in ACCOUNT_TYPES:
            return CustomerResult.fail("Tipo de cuenta no válido.", "VALIDATION",
                                       operation_id=operation_id)
        if company_size and company_size not in COMPANY_SIZES:
            return CustomerResult.fail("Tamaño de empresa no válido.", "VALIDATION",
                                       operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if uow.customers.get(customer_id) is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if parent_account_id and uow.accounts.get(parent_account_id) is None:
                return CustomerResult.fail("La cuenta padre no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            account = CustomerAccount.create(
                customer_id, account_type=account_type, industry=industry.strip(),
                company_size=company_size, website=website.strip(),
                parent_account_id=parent_account_id)
            uow.accounts.save(account)
            self._record(uow, actor_user_id, account, "alta de cuenta comercial", operation_id)
        return CustomerResult.ok("Cuenta comercial registrada", entity_id=account.id,
                                 operation_id=operation_id)


class UpdateCustomerAccountUseCase(_Base):
    def execute(self, connection, *, actor_user_id: str, account_id: str, operation_id: str,
                account_type: str | None = None, industry: str | None = None,
                company_size: str | None = None, website: str | None = None,
                status: str | None = None) -> CustomerResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        if account_type is not None and account_type not in ACCOUNT_TYPES:
            return CustomerResult.fail("Tipo de cuenta no válido.", "VALIDATION",
                                       operation_id=operation_id)
        if company_size and company_size not in COMPANY_SIZES:
            return CustomerResult.fail("Tamaño de empresa no válido.", "VALIDATION",
                                       operation_id=operation_id)
        if status is not None and status not in ("ACTIVE", "INACTIVE"):
            return CustomerResult.fail("Estatus de cuenta no válido.", "VALIDATION",
                                       operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            account = uow.accounts.get(account_id)
            if account is None:
                return CustomerResult.fail("La cuenta no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            for name, value in (("account_type", account_type), ("industry", industry),
                                ("company_size", company_size), ("website", website),
                                ("status", status)):
                if value is not None:
                    setattr(account, name, value.strip() if isinstance(value, str) else value)
            uow.accounts.update(account)
            self._record(uow, actor_user_id, account, "edición de cuenta comercial", operation_id)
        return CustomerResult.ok("Cuenta comercial actualizada", entity_id=account_id,
                                 operation_id=operation_id)
