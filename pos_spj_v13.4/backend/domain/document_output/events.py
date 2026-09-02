"""Canonical Document Output domain events — SET-11 (§61). Mirrors
backend/domain/settings/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class DocumentOutputEvents:
    TEMPLATE_CREATED = "DOCUMENT_TEMPLATE_CREATED"
    TEMPLATE_APPROVED = "DOCUMENT_TEMPLATE_APPROVED"
    TEMPLATE_ACTIVATED = "DOCUMENT_TEMPLATE_ACTIVATED"
    TEMPLATE_REJECTED = "DOCUMENT_TEMPLATE_REJECTED"
    TEMPLATE_ARCHIVED = "DOCUMENT_TEMPLATE_ARCHIVED"

    PRINT_JOB_CREATED = "PRINT_JOB_CREATED"
    PRINT_JOB_RENDERING = "PRINT_JOB_RENDERING"
    PRINT_JOB_READY = "PRINT_JOB_READY"
    PRINT_JOB_PRINTED = "PRINT_JOB_PRINTED"
    PRINT_JOB_FAILED = "PRINT_JOB_FAILED"
    PRINT_JOB_CANCELLED = "PRINT_JOB_CANCELLED"
    PRINT_JOB_RETRIED = "PRINT_JOB_RETRIED"
    PRINT_JOB_DEAD_LETTERED = "PRINT_JOB_DEAD_LETTERED"
    DOCUMENT_REPRINTED = "DOCUMENT_REPRINTED"


ALL_DOCUMENT_OUTPUT_EVENTS = frozenset(
    value for key, value in vars(DocumentOutputEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, job_id: str | None = None,
    template_id: str | None = None, template_version_id: str | None = None,
    user_id: str | None = None, source_module: str = "document_output", **extra,
) -> dict:
    """Build the canonical minimum payload for a Document Output event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "job_id": job_id,
        "template_id": template_id,
        "template_version_id": template_version_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload
