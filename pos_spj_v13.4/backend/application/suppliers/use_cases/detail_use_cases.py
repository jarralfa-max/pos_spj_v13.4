"""Supplier detail use cases: contacts, addresses, bank accounts (+ verification),
commercial terms, product assignment, documents, branch authorization.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.permissions import SupplierPermissions
from backend.application.suppliers.result import SupplierResult
from backend.application.suppliers.use_cases.lifecycle_use_cases import _BaseUseCase
from backend.domain.suppliers.entities import (
    SupplierAddress,
    SupplierBankAccount,
    SupplierBranchAuthorization,
    SupplierCommercialTerms,
    SupplierContact,
    SupplierDocument,
    SupplierProduct,
)
from backend.domain.suppliers.enums import (
    AddressType,
    ContactType,
    DocumentType,
)
from backend.domain.suppliers.events import SupplierEvents
from backend.domain.suppliers.exceptions import PermissionDeniedError, SupplierDomainError
from backend.domain.suppliers.value_objects import Money, PaymentTerms
from backend.infrastructure.db.repositories.suppliers.unit_of_work import SupplierUnitOfWork


def _deny(exc, operation_id):
    return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)


class AddSupplierContactUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, name: str,
                contact_type: str, operation_id: str, **fields) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                contact = SupplierContact.create(supplier_id, name, ContactType(contact_type),
                                                 **fields)
            except (SupplierDomainError, ValueError) as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.contacts.save(contact)
            uow.audit.record(action="SUPPLIER_CONTACT_ADDED", actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason="", operation_id=operation_id)
        return SupplierResult.ok("Contacto agregado", entity_id=contact.id,
                                 operation_id=operation_id)


class AddSupplierAddressUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, address_type: str,
                line: str, operation_id: str, **fields) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            address = SupplierAddress.create(supplier_id, AddressType(address_type), line, **fields)
            uow.addresses.save(address)
            uow.audit.record(action="SUPPLIER_ADDRESS_ADDED", actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason="", operation_id=operation_id)
        return SupplierResult.ok("Dirección agregada", entity_id=address.id,
                                 operation_id=operation_id)


class AddSupplierBankAccountUseCase(_BaseUseCase):
    """New bank data never enables payment immediately — the account is UNVERIFIED
    and must pass the verification workflow (SUPPLIER_BANK_ACCOUNT_CHANGED)."""

    def execute(self, connection, *, actor_user_id: str, supplier_id: str, bank_name: str,
                account_holder: str, operation_id: str, **fields) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT_BANK)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            account = SupplierBankAccount.create(supplier_id, bank_name, account_holder, **fields)
            uow.bank_accounts.save(account)
            # audit stores masked CLABE only (never the raw number)
            uow.audit.record(action=SupplierEvents.BANK_ACCOUNT_CHANGED,
                             actor_user_id=actor_user_id, supplier_id=supplier_id,
                             after_json=json.dumps({"bank": bank_name,
                                                     "clabe": account.masked_clabe()}),
                             reason="alta cuenta", operation_id=operation_id)
            self._emit(uow, SupplierEvents.BANK_ACCOUNT_CHANGED, supplier_id, operation_id,
                       actor_user_id, bank_account_id=account.id)
        return SupplierResult.ok("Cuenta bancaria registrada (pendiente de verificación)",
                                 entity_id=account.id, operation_id=operation_id)


class VerifySupplierBankAccountUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, bank_account_id: str,
                operation_id: str) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.VERIFY_BANK)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            account = uow.bank_accounts.get(bank_account_id)
            if account is None:
                return SupplierResult.fail("La cuenta no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            from backend.domain.suppliers.enums import BankAccountStatus
            if account.status is BankAccountStatus.VERIFIED:
                return SupplierResult.ok("La cuenta ya estaba verificada",
                                         entity_id=bank_account_id, operation_id=operation_id)
            try:
                account.verify(actor_user_id)
            except SupplierDomainError as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.bank_accounts.update(account)
            uow.audit.record(action=SupplierEvents.BANK_ACCOUNT_VERIFIED,
                             actor_user_id=actor_user_id, supplier_id=account.supplier_id,
                             reason="verificación", operation_id=operation_id)
            self._emit(uow, SupplierEvents.BANK_ACCOUNT_VERIFIED, account.supplier_id,
                       operation_id, actor_user_id, bank_account_id=account.id)
        return SupplierResult.ok("Cuenta bancaria verificada", entity_id=bank_account_id,
                                 operation_id=operation_id)


class UpdateSupplierCommercialTermsUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, operation_id: str,
                credit_days: int = 0, credit_limit: str = "0", currency_code: str = "MXN",
                advance_required: bool = False, advance_percentage: str = "0",
                prompt_payment_discount: str = "0", min_order_amount: str = "0",
                lead_time_days: int = 0, receiving_window_start: str | None = None,
                receiving_window_end: str | None = None) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT_TERMS)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                pt = PaymentTerms(
                    credit_days=credit_days,
                    credit_limit=Money(Decimal(credit_limit), currency_code),
                    advance_required=advance_required,
                    advance_percentage=Decimal(advance_percentage),
                    prompt_payment_discount=Decimal(prompt_payment_discount),
                    min_order_amount=Money(Decimal(min_order_amount), currency_code))
                terms = SupplierCommercialTerms.create(
                    supplier_id, pt, currency_code=currency_code, lead_time_days=lead_time_days,
                    receiving_window_start=receiving_window_start,
                    receiving_window_end=receiving_window_end)
            except SupplierDomainError as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.terms.upsert(terms)
            uow.audit.record(action=SupplierEvents.TERMS_UPDATED, actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason="", operation_id=operation_id)
            self._emit(uow, SupplierEvents.TERMS_UPDATED, supplier_id, operation_id, actor_user_id)
        return SupplierResult.ok("Condiciones comerciales actualizadas", entity_id=supplier_id,
                                 operation_id=operation_id)


class AssignProductToSupplierUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, product_id: str,
                operation_id: str, current_cost: str | None = None, currency_code: str = "MXN",
                preferred: bool = False, **fields) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            product = SupplierProduct.create(
                supplier_id, product_id, currency_code=currency_code, preferred=preferred,
                current_cost=Money(Decimal(current_cost), currency_code) if current_cost else None,
                **fields)
            uow.products.upsert(product)
            uow.audit.record(action=SupplierEvents.PRODUCT_ASSIGNED, actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason=product_id, operation_id=operation_id)
            self._emit(uow, SupplierEvents.PRODUCT_ASSIGNED, supplier_id, operation_id,
                       actor_user_id, product_id=product_id)
        return SupplierResult.ok("Producto asignado al proveedor", entity_id=product.id,
                                 operation_id=operation_id)


class UploadSupplierDocumentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, document_type: str,
                file_reference: str, operation_id: str, issued_at: str | None = None,
                expires_at: str | None = None) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.UPLOAD_DOCUMENTS)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            doc = SupplierDocument.create(
                supplier_id, DocumentType(document_type), file_reference,
                issued_at=date.fromisoformat(issued_at) if issued_at else None,
                expires_at=date.fromisoformat(expires_at) if expires_at else None)
            uow.documents.save(doc)
            uow.audit.record(action="SUPPLIER_DOCUMENT_UPLOADED", actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason=document_type, operation_id=operation_id)
        return SupplierResult.ok("Documento cargado", entity_id=doc.id, operation_id=operation_id)


class AuthorizeSupplierBranchUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, branch_id: str,
                operation_id: str, can_purchase: bool = True, can_receive: bool = True,
                can_pay: bool = True, preferred: bool = False) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT)
        except PermissionDeniedError as exc:
            return _deny(exc, operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            auth = SupplierBranchAuthorization.create(
                supplier_id, branch_id, can_purchase=can_purchase, can_receive=can_receive,
                can_pay=can_pay, preferred=preferred)
            uow.branches.upsert(auth)
            uow.audit.record(action="SUPPLIER_BRANCH_AUTHORIZED", actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason=branch_id, operation_id=operation_id)
        return SupplierResult.ok("Autorización por sucursal registrada", entity_id=auth.id,
                                 operation_id=operation_id)
