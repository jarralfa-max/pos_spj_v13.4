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

import logging

from backend.application.sales.dto import SaleDTO, SaleReceiptDataDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import ReceiptNotAvailableError, SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient
from backend.infrastructure.integrations.sales_marketing_client import SalesMarketingClient
from backend.infrastructure.integrations.sales_print_job_client import SalesPrintJobClient
from backend.infrastructure.integrations.sales_receipt_client import SalesReceiptClient
from backend.infrastructure.integrations.sales_sweepstakes_client import SalesSweepstakesClient

logger = logging.getLogger(__name__)


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
        reason: str = "Reimpresión de ticket",
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

            print_job = _try_track_print_job(
                connection, sale_id=sale.id, branch_id=sale.branch_id, actor_user_id=actor_user_id,
                is_reprint=True, reprint_reason=reason)
            loyalty = _try_peek_loyalty(connection, sale.customer_id)
            messages = _try_select_messages(
                connection, subtotal=receipt.subtotal, total=receipt.total,
                has_customer=sale.customer_id is not None,
                points_balance=loyalty.points_balance if loyalty else None)
            job_id = SalesReceiptClient(printer_service).print_receipt_data(
                receipt, loyalty=loyalty, messages=messages,
                on_success=_mark_job_printed(connection, print_job),
                on_error=_mark_job_failed(connection, print_job))
            self._emit(uow, SaleEvents.RECEIPT_REPRINT_REQUESTED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, job_id=job_id, folio=receipt.folio)

        raffle_tickets_printed = _try_print_raffle_tickets(connection, printer_service, sale_id=sale.id)
        return SaleResult.ok(
            "Reimpresión enviada", entity_id=sale.id, operation_id=operation_id,
            receipt=receipt, job_id=job_id, raffle_tickets_printed=raffle_tickets_printed)


def _try_track_print_job(connection, *, sale_id, branch_id, actor_user_id, is_reprint, reprint_reason):
    """Best-effort `document_output.PrintJob` audit/routing record for this
    print — see `sales_print_job_client.py`'s own docstring. Never allowed
    to block or fail a real ticket print: any error here is logged and
    swallowed, and the caller proceeds with the legacy print path exactly
    as if this integration didn't exist."""
    try:
        return SalesPrintJobClient(connection).try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id=actor_user_id,
            is_reprint=is_reprint, reprint_reason=reprint_reason)
    except Exception:  # noqa: BLE001 - audit-only integration, never break a real print
        logger.exception("No se pudo registrar PrintJob de Document Output para venta %s", sale_id)
        return None


def _try_peek_loyalty(connection, customer_id: str | None):
    """Best-effort, side-effect-free loyalty balance/tier lookup — see
    `sales_loyalty_client.py::peek_loyalty_summary`'s own docstring. Never
    allowed to block a real ticket print."""
    if customer_id is None:
        return None
    try:
        return SalesLoyaltyClient(connection).peek_loyalty_summary(customer_id=customer_id)
    except Exception:  # noqa: BLE001 - audit-only integration, never break a real print
        logger.exception("No se pudo consultar el resumen de fidelidad para cliente %s", customer_id)
        return None


def _try_select_messages(connection, *, subtotal, total, has_customer, points_balance):
    """Best-effort marketing message selection — see
    `sales_marketing_client.py`'s own docstring. Never allowed to block a
    real ticket print."""
    try:
        return SalesMarketingClient(connection).select_ticket_messages(
            subtotal=subtotal, total=total, has_customer=has_customer, points_balance=points_balance)
    except Exception:  # noqa: BLE001 - audit-only integration, never break a real print
        logger.exception("No se pudo seleccionar mensajes de marketing para el ticket")
        return ()


def _try_print_raffle_tickets(connection, printer_service, *, sale_id: str) -> int:
    """Best-effort real raffle/sweepstakes ticket printing — see
    `sales_sweepstakes_client.py`'s own docstring (SET-15 cutover). Prints
    every previously-issued boleto for this sale via the same real,
    already-live `PrinterService.print_raffle_ticket()` the legacy
    `SalesService` path uses. Never allowed to block the receipt print —
    a bad ticket payload or lookup failure is logged and swallowed, same
    discipline as every other integration in this use case."""
    try:
        payloads = SalesSweepstakesClient(connection).get_printable_tickets_for_sale(sale_id=sale_id)
    except Exception:  # noqa: BLE001 - audit-only integration, never break a real print
        logger.exception("No se pudieron consultar boletos de rifa para venta %s", sale_id)
        return 0

    printed = 0
    for payload in payloads:
        try:
            printer_service.print_raffle_ticket(payload)
            printed += 1
        except Exception:  # noqa: BLE001 - one bad ticket must not block the others or the receipt
            logger.exception("No se pudo imprimir boleto de rifa para venta %s", sale_id)
    return printed


def _mark_job_printed(connection, print_job):
    if print_job is None:
        return None

    def _on_success() -> None:
        try:
            SalesPrintJobClient(connection).mark_printed(print_job)
        except Exception:  # noqa: BLE001 - audit-only, never break the success callback
            logger.exception("No se pudo marcar PrintJob %s como impreso", print_job.id)
    return _on_success


def _mark_job_failed(connection, print_job):
    if print_job is None:
        return None

    def _on_error(exc: Exception) -> None:
        try:
            SalesPrintJobClient(connection).mark_failed(print_job, str(exc))
        except Exception:  # noqa: BLE001 - audit-only, never break the error callback
            logger.exception("No se pudo marcar PrintJob %s como fallido", print_job.id)
    return _on_error


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
