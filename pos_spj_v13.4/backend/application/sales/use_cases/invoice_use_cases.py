"""Invoice use cases (POS-18/§15/§46: "Fiscal" — Invoice request, Status,
Errors, Tests).

Research for this phase confirmed NO working PAC (Facturama/SW Sapien/
Finkok/etc.) integration exists anywhere in this repository — both legacy
CFDI services are either a stub, an unconfigured generic HTTP client, or
(the one actually wired into the live UI, `core/services/cfdi_service.py::
CFDIService`) crashing with a `NameError` on every single call due to a
missing import (fixed as a narrow, SALES-9-style correction alongside this
phase — see that file's own diff — but NOT wired here: it operates on
LEGACY `ventas`/`detalles_venta` ids, which the new `Sale` aggregate never
populates, so calling it with a new-stack `sale.id` would only ever return
"Venta no encontrada", never a real result).

Given that, this phase builds exactly what master prompt §15 says Sales
itself owns — "Ventas conserva snapshots históricos" — and nothing more:
`RequestInvoiceUseCase` records a real request (resolving RFC/legal name/
CFDI-use from Customer Master's real `CustomerTaxProfile` when the sale has
an assigned customer, §15's actual master-data owner), and
`MarkInvoiceIssuedUseCase`/`MarkInvoiceErrorUseCase` are the real resolution
API a future Fiscal bounded context (or a manual reconciliation) would call
once real stamping exists — not a fabricated auto-success.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_fiscal_client import SalesFiscalClient

_WALK_IN_RFC = "XAXX010101000"
_WALK_IN_NAME = "PUBLICO EN GENERAL"
_DEFAULT_CFDI_USE = "S01"


class RequestInvoiceUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, actor_user_id: str, operation_id: str,
        tax_identifier: str | None = None, legal_name: str | None = None,
        cfdi_use: str | None = None,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.INVOICE_REQUEST)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            resolved_tax_id, resolved_name, resolved_use = tax_identifier, legal_name, cfdi_use
            if not resolved_tax_id and sale.customer_id:
                profile = SalesFiscalClient(connection).resolve_tax_profile(sale.customer_id)
                if profile:
                    resolved_tax_id = resolved_tax_id or profile["tax_identifier"]
                    resolved_name = resolved_name or profile["legal_name"]
                    resolved_use = resolved_use or profile["cfdi_use"]
            resolved_tax_id = resolved_tax_id or _WALK_IN_RFC
            resolved_name = resolved_name or _WALK_IN_NAME
            resolved_use = resolved_use or _DEFAULT_CFDI_USE

            try:
                request = sale.request_invoice(
                    tax_identifier=resolved_tax_id, legal_name=resolved_name,
                    cfdi_use=resolved_use, requested_by_user_id=actor_user_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.INVOICE_REQUESTED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, invoice_request_id=request.id,
                       tax_identifier=resolved_tax_id)
        return SaleResult.ok(
            "Factura solicitada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), invoice_request_id=request.id)


class MarkInvoiceIssuedUseCase(_SalesBaseUseCase):
    """The real resolution a future Fiscal/PAC integration (or a manual
    reconciliation) calls once an actual UUID fiscal exists — never called
    speculatively by anything in this phase."""

    def execute(
        self, connection, *, sale_id: str, invoice_request_id: str, uuid_fiscal: str,
        actor_user_id: str, operation_id: str,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.INVOICE_REQUEST)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.mark_invoice_issued(invoice_request_id, uuid_fiscal=uuid_fiscal)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.INVOICE_ISSUED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, invoice_request_id=invoice_request_id,
                       uuid_fiscal=uuid_fiscal)
        return SaleResult.ok(
            "Factura timbrada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale))


class MarkInvoiceErrorUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, invoice_request_id: str, error_message: str,
        actor_user_id: str, operation_id: str,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.INVOICE_REQUEST)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.mark_invoice_error(invoice_request_id, error_message=error_message)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.INVOICE_ERROR, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, invoice_request_id=invoice_request_id,
                       error_message=error_message)
        return SaleResult.ok(
            "Error de facturación registrado", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale))
