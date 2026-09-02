"""SalesPrintJobClient — Sales' integration point onto Document Output's
`PrintJob` routing/reprint governance (SET-12 cutover). Mirrors
`sales_receipt_client.py`/`document_output_print_routing_client.py`'s
shape: thin, delegates entirely to the owning contexts' real policies and
repositories.

**Audit/governance only** — this never influences whether or how a real
ticket is physically printed. Actual byte rendering and dispatch stay on
`core/services/printer_service.py::PrinterService`/`TicketESCPOSRenderer`,
untouched. `printer_device_id`/`print_route_id` are recorded here for
audit purposes only.

**The central safety property**: every method degrades to `None` (a
no-op) whenever a `SALE_TICKET` template/version or a matching
`PrintRoute` isn't configured yet, or route resolution fails for any
reason — a real ticket must never fail to print because of this. No
admin has configured either prerequisite in the live DB as of this
writing; both are already reachable via the live Configuración
Documentos/Dispositivos screens (`SALE_TICKET` is one of `DocumentType`'s
existing values, no new UI needed).
"""

from __future__ import annotations

import logging

from backend.domain.device_management.exceptions import NoAvailablePrinterError, PrintRouteNotFoundError
from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import DocumentType
from backend.domain.document_output.exceptions import DocumentReprintNotAllowedError
from backend.domain.document_output.policies.reprint_policy import request_reprint
from backend.domain.document_output.policies.ticket_routing_policy import create_routed_print_job
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)
from backend.infrastructure.db.repositories.document_output.print_job_repository import SqlitePrintJobRepository
from backend.infrastructure.integrations.document_output_print_routing_client import (
    DocumentOutputPrintRoutingClient,
)

logger = logging.getLogger(__name__)

_SOURCE_MODULE = "sales"


class SalesPrintJobClient:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._templates = SqliteDocumentTemplateRepository(connection)
        self._versions = SqliteDocumentTemplateVersionRepository(connection)
        self._jobs = SqlitePrintJobRepository(connection)

    def try_create_or_reprint_job(
        self, *, sale_id: str, branch_id: str, actor_user_id: str,
        is_reprint: bool, reprint_reason: str,
    ) -> PrintJob | None:
        version_id = self._active_sale_ticket_version_id()
        if version_id is None:
            return None

        previous = self._jobs.list_by_source(_SOURCE_MODULE, sale_id) if is_reprint else []
        if previous:
            # A prior job for this sale exists: this print is governed by
            # reprint_policy, not fresh routing — and if the prior job isn't
            # reprintable yet (still in flight), this is a governance skip,
            # never a fall-through to an unrelated fresh job.
            try:
                job = request_reprint(previous[0], requested_by_user_id=actor_user_id, reason=reprint_reason)
            except DocumentReprintNotAllowedError:
                logger.info("Reimpresión de ticket omitida para venta %s: job previo no reimprimible", sale_id)
                return None
        else:
            job = self._create_routed(version_id, sale_id=sale_id, branch_id=branch_id,
                                       actor_user_id=actor_user_id)
        if job is None:
            return None

        job.start_rendering()
        job.mark_ready()
        job.start_printing()
        self._jobs.save(job)
        return job

    def mark_printed(self, job: PrintJob) -> None:
        job.mark_printed()
        self._jobs.save(job)

    def mark_failed(self, job: PrintJob, reason: str) -> None:
        job.fail(reason or "Error de impresión")
        self._jobs.save(job)

    # internals -----------------------------------------------------------------
    def _active_sale_ticket_version_id(self) -> str | None:
        templates = self._templates.list_by_document_type(DocumentType.SALE_TICKET)
        template = next((t for t in templates if t.active), None)
        if template is None:
            return None
        version = self._versions.get_active_for_template(template.id)
        return version.id if version is not None else None

    def _create_routed(
        self, version_id: str, *, sale_id: str, branch_id: str, actor_user_id: str,
    ) -> PrintJob | None:
        resolver = DocumentOutputPrintRoutingClient(
            SqlitePrintRouteRepository(self._connection), SqliteDeviceRepository(self._connection))
        try:
            return create_routed_print_job(
                resolver, document_type=DocumentType.SALE_TICKET.value, source_module=_SOURCE_MODULE,
                source_document_id=sale_id, template_version_id=version_id,
                requested_by_user_id=actor_user_id, branch_id=branch_id,
            )
        except (PrintRouteNotFoundError, NoAvailablePrinterError) as exc:
            logger.info("Sin ruta de impresión configurada para SALE_TICKET (venta %s): %s", sale_id, exc)
            return None
