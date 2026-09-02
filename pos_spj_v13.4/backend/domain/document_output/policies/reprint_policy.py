"""ReprintPolicy — SET-12 "Reimpresión": *when* a reprint is allowed, on
top of `PrintJob.create_reprint()` (SET-11), which only enforces *how* a
reprint is shaped (a new job, chained by `reprint_of_job_id`, always with
a reason) and deliberately allows it from any status — see
`tests/unit/document_output/test_print_job_lifecycle.py::
TestCreateReprint::test_reprint_can_be_requested_regardless_of_original_status`.
That entity-level permissiveness is intentional and unchanged by this
policy: `create_reprint()` stays the low-level mechanical operation;
`request_reprint()` here is the stricter, business-rule-enforced entry
point callers should actually use.

Rule: a job can only be reprinted once it has left its first attempt in
flight — PENDING/RENDERING/READY/PRINTING never printed (or definitively
gave up) yet, so "reprint" doesn't apply to them. PRINTED (the normal
case), FAILED and DEAD_LETTER (something went wrong, a person is manually
retrying), and CANCELLED (the request is being made again) are all valid.

Permission/authorization (e.g. Sales' own `POS.ticket.reimprimir`, or
whatever the equivalent is per consuming module) is deliberately NOT
checked here — that is an application-layer, per-module concern, the
same layering `backend/application/sales/use_cases/receipt_use_cases.py::
ReprintReceiptUseCase` already applies for Sales specifically. This
bounded context has no dependency on any permission catalog.
"""

from __future__ import annotations

from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import PrintJobStatus
from backend.domain.document_output.exceptions import DocumentReprintNotAllowedError

_REPRINTABLE_STATUSES = {
    PrintJobStatus.PRINTED, PrintJobStatus.FAILED, PrintJobStatus.CANCELLED, PrintJobStatus.DEAD_LETTER,
}


def assert_reprintable(original: PrintJob) -> None:
    if original.status not in _REPRINTABLE_STATUSES:
        raise DocumentReprintNotAllowedError(
            f"No se puede reimprimir un job en estado {original.status.value}"
        )


def request_reprint(original: PrintJob, *, requested_by_user_id: str, reason: str) -> PrintJob:
    assert_reprintable(original)
    return original.create_reprint(requested_by_user_id=requested_by_user_id, reason=reason)
