"""Receipt use cases (POS-17/§46: Receipt DTO, PrintJob, Reprint, PDF).

`ReprintReceiptUseCase` is the real gap this phase closes: no equivalent
existed anywhere in `backend/application/sales` before now — the legacy
`modulos/ventas.py::_reimprimir_ultima_venta` only reprints the single most
recent sale from a raw SQL read, with no permission re-check beyond the
Devolución-button-style gate. This use case works for ANY completed sale
by id, always re-checks `SalesPermissions.RECEIPT_REPRINT`, and derives the
original payment breakdown from `Sale.payments` (SALES-13) instead of
requiring the caller to remember it.

`SaveReceiptDocumentUseCase` is the "PDF" bullet — see
`sales_receipt_client.py`'s own docstring for how it renders through the
same real `TicketTemplateEngine` the live `SalesService` sale-completion
path already uses, so the saved document matches production exactly.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO, SaleReceiptDataDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import ReceiptNotAvailableError, SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_receipt_client import SalesReceiptClient


def _load_receipt_data(uow, sale_id: str, *, cajero_nombre: str, cliente_nombre: str):
    sale = uow.sales.get(sale_id)
    if sale is None:
        raise SaleNotFoundError(f"Venta {sale_id} no existe")
    if sale.completed_at is None:
        raise ReceiptNotAvailableError(
            f"La venta {sale_id} nunca completó el cobro — no hay ticket que emitir")
    sale_dto = SaleDTO.from_entity(sale)
    receipt = SalesReceiptClient.build_receipt_data_from_sale(
        sale_dto, cajero_nombre=cajero_nombre, cliente_nombre=cliente_nombre)
    return sale, receipt


class ReprintReceiptUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, printer_service, *, sale_id: str, cajero_nombre: str,
        actor_user_id: str, operation_id: str, cliente_nombre: str = "Público General",
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.RECEIPT_REPRINT)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            try:
                sale, receipt = _load_receipt_data(
                    uow, sale_id, cajero_nombre=cajero_nombre, cliente_nombre=cliente_nombre)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            job_id = SalesReceiptClient(printer_service).print_receipt_data(receipt)
            self._emit(uow, SaleEvents.RECEIPT_REPRINT_REQUESTED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, job_id=job_id, folio=receipt.folio)
        return SaleResult.ok(
            "Reimpresión enviada", entity_id=sale.id, operation_id=operation_id,
            receipt=receipt, job_id=job_id)


class SaveReceiptDocumentUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, filepath: str, cajero_nombre: str,
        actor_user_id: str, operation_id: str, cliente_nombre: str = "Público General",
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.VIEW)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            try:
                sale, receipt = _load_receipt_data(
                    uow, sale_id, cajero_nombre=cajero_nombre, cliente_nombre=cliente_nombre)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            saved_path = SalesReceiptClient(connection=connection).save_receipt_document(
                receipt, filepath)
        return SaleResult.ok(
            "Documento guardado", entity_id=sale.id, operation_id=operation_id,
            receipt=receipt, filepath=saved_path)
