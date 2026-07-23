"""InventoryLabelPrintService (INV-26).

``print_label`` is the single canonical print route: it re-validates the granular
permission (LABEL_PRINT, or LABEL_REPRINT for a reprint), hands the rendered
LabelDocument to the print gateway, writes an audit row to
``inventory_label_print_log`` (the reprint trail), and — when an event dispatcher
is wired — emits INVENTORY_LABEL_PRINTED / INVENTORY_LABEL_REPRINTED. A gateway
delivery failure is audited (never crashes the caller).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.labels.gateway import (
    InMemoryPrintGateway,
    PrintDeliveryError,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.enums import LabelFormat
from backend.domain.inventory.events import InventoryEvents
from backend.domain.inventory.exceptions import InventoryPermissionDeniedError
from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InventoryLabelPrintService:
    def __init__(self, connection, gateway=None,
                 authorization: InventoryAuthorizationPolicy | None = None,
                 event_dispatcher=None) -> None:
        self._conn = connection
        self._gateway = gateway or InMemoryPrintGateway()
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._dispatch = event_dispatcher

    def print_label(self, document: LabelDocument, *, actor_user_id: str,
                    printer_ref: str = "default",
                    label_format: LabelFormat = LabelFormat.ESCPOS,
                    is_reprint: bool = False, reason: str | None = None,
                    branch_id: str | None = None) -> InventoryResult:
        permission = (InventoryPermissions.LABEL_REPRINT if is_reprint
                      else InventoryPermissions.LABEL_PRINT)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")

        copies = int(document.copies)
        failed = None
        try:
            self._gateway.print(document=document, printer_ref=printer_ref,
                                label_format=label_format, copies=copies)
        except PrintDeliveryError as exc:
            failed = str(exc)

        log_id = self._audit(document, printer_ref=printer_ref,
                             label_format=label_format, copies=copies,
                             is_reprint=is_reprint, reason=reason or failed,
                             branch_id=branch_id, actor_user_id=actor_user_id)
        self._conn.commit()

        if failed is not None:
            return InventoryResult.fail(f"Impresión falló: {failed}",
                                        "PRINT_DELIVERY_FAILED", entity_id=log_id)

        if self._dispatch is not None:
            event = (InventoryEvents.INVENTORY_LABEL_REPRINTED if is_reprint
                     else InventoryEvents.INVENTORY_LABEL_PRINTED)
            self._dispatch(event, {"label_id": log_id,
                                   "label_type": document.label_type.value,
                                   "entity_ref": document.entity_ref,
                                   "user_id": actor_user_id})
        return InventoryResult.ok("Etiqueta impresa", entity_id=log_id)

    def _audit(self, document: LabelDocument, *, printer_ref, label_format, copies,
               is_reprint, reason, branch_id, actor_user_id) -> str:
        log_id = new_uuid()
        self._conn.execute(
            "INSERT INTO inventory_label_print_log"
            " (id, label_type, label_format, entity_ref, printer_ref, copies,"
            "  is_reprint, reason, title, branch_id, printed_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (log_id, document.label_type.value, label_format.value,
             document.entity_ref, printer_ref, copies, 1 if is_reprint else 0,
             reason, document.title, branch_id, actor_user_id, _now()))
        return log_id
