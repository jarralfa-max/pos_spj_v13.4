"""SaleInvoicePolicy — POS-18/§15/§46 invariants for requesting a CFDI
invoice against a Sale."""

from __future__ import annotations

from backend.domain.sales.enums import InvoiceStatus, SaleStatus
from backend.domain.sales.exceptions import (
    InvoiceAlreadyPendingError,
    InvoiceRequestNotAllowedError,
    InvoiceTransitionNotAllowedError,
)

_INVOICEABLE_STATUSES = frozenset({
    SaleStatus.COMPLETED, SaleStatus.RETURNED_PARTIALLY, SaleStatus.RETURNED_FULLY,
})


class SaleInvoicePolicy:
    @staticmethod
    def ensure_can_request(*, status: SaleStatus, tax_identifier: str,
                           existing_requests) -> None:
        if status not in _INVOICEABLE_STATUSES:
            raise InvoiceRequestNotAllowedError(
                f"No se puede facturar una venta en estado {status.value}")
        if not (tax_identifier or "").strip():
            raise InvoiceRequestNotAllowedError("La factura requiere un RFC")
        if any(r.status is InvoiceStatus.REQUESTED for r in existing_requests):
            raise InvoiceAlreadyPendingError(
                "Ya existe una solicitud de factura pendiente para esta venta")

    @staticmethod
    def normalize_fiscal_uuid(value: str) -> str:
        """El folio fiscal (UUID del timbre del SAT): 8-4-4-4-12 hexadecimal.
        Se guarda en mayúsculas, como lo imprime el CFDI."""
        import re
        text = (value or "").strip().upper()
        if not re.fullmatch(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", text):
            raise InvoiceTransitionNotAllowedError(
                "El folio fiscal (UUID) debe tener el formato del SAT: "
                "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        return text

    @staticmethod
    def ensure_can_resolve(status: InvoiceStatus) -> None:
        if status is not InvoiceStatus.REQUESTED:
            raise InvoiceTransitionNotAllowedError(
                f"Solo una solicitud REQUESTED puede resolverse (actual: {status.value})")
