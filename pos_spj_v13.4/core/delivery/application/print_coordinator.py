"""DeliveryPrintCoordinator — prints delivery documents on status transitions,
idempotently, AFTER the state change has been committed.

Rules (from SPJ_REFACTOR_SKILL / delivery defects 5,6):
  - Document selection comes from DeliveryPrintPolicy (single source of truth).
  - A printer failure must NOT revert an already-committed transition; the
    document is recorded as pending re-print instead.
  - A retry must never print the same document twice — idempotency is enforced
    by the unique (delivery_id, document_type) row in delivery_print_log.

The actual rendering is delegated to a printer port (default: TicketPrinterService)
so this coordinator stays free of Qt/hardware concerns and is unit-testable.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.delivery.domain.print_policy import DeliveryDocument, DeliveryPrintPolicy

logger = logging.getLogger("spj.delivery.application.print")


class DeliveryPrintCoordinator:
    def __init__(
        self,
        db,
        *,
        printer_factory: Callable[[], Any] | None = None,
        policy: DeliveryPrintPolicy | None = None,
    ) -> None:
        self.db = db
        self.policy = policy or DeliveryPrintPolicy()
        # Lazily builds a printer with a print_customer_ticket/print_driver_ticket API.
        self._printer_factory = printer_factory

    def print_for_transition(self, order: dict[str, Any], status: str) -> None:
        """Print the documents required for *status*. Never raises."""
        order_id = order.get("id") or order.get("order_id")
        workflow = order.get("workflow_type") or order.get("delivery_type") or ""
        documents = self.policy.documents_for(status, workflow)
        for document in documents:
            self._print_once(order_id, document)

    # ── internals ────────────────────────────────────────────────────────────

    def _print_once(self, order_id, document: DeliveryDocument) -> None:
        if order_id is None:
            return
        if self._already_printed(order_id, document):
            logger.info("print skip (already printed) order=%s doc=%s", order_id, document.value)
            return
        try:
            ok = self._render(order_id, document)
        except Exception as exc:
            ok = False
            logger.warning("print render failed order=%s doc=%s: %s", order_id, document.value, exc)
        # Record outcome: 'printed' or 'pending' (for later re-print) — idempotent.
        self._record(order_id, document, status="printed" if ok else "pending")

    def _already_printed(self, order_id, document: DeliveryDocument) -> bool:
        try:
            row = self.db.execute(
                "SELECT status FROM delivery_print_log "
                "WHERE delivery_id=? AND document_type=?",
                (order_id, document.value),
            ).fetchone()
        except Exception:
            return False
        if not row:
            return False
        status = row[0] if not hasattr(row, "keys") else row["status"]
        return status == "printed"

    def _record(self, order_id, document: DeliveryDocument, status: str) -> None:
        try:
            # Insert-or-promote: keep the row unique; only upgrade pending→printed.
            self.db.execute(
                "INSERT INTO delivery_print_log (delivery_id, document_type, status) "
                "VALUES (?,?,?) "
                "ON CONFLICT(delivery_id, document_type) DO UPDATE SET "
                "status=CASE WHEN delivery_print_log.status='printed' THEN 'printed' ELSE excluded.status END, "
                "printed_at=CURRENT_TIMESTAMP",
                (order_id, document.value, status),
            )
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as exc:
            logger.debug("print log record failed order=%s doc=%s: %s", order_id, document.value, exc)

    def _render(self, order_id, document: DeliveryDocument) -> bool:
        printer = self._build_printer()
        if printer is None:
            return False
        if document == DeliveryDocument.DRIVER_OPERATIVE:
            return bool(printer.print_driver_ticket(order_id))
        if document == DeliveryDocument.CUSTOMER_RECEIPT:
            return bool(printer.print_customer_ticket(order_id))
        return False

    def _build_printer(self):
        if self._printer_factory is not None:
            return self._printer_factory()
        try:
            from core.services.ticket_printer_service import TicketPrinterService
            return TicketPrinterService(self.db)
        except Exception as exc:
            logger.debug("no printer available: %s", exc)
            return None
