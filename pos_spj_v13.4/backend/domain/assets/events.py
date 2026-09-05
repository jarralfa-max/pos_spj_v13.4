"""Canonical integration events for the Assets / EAM bounded context (§53, §87).

These are contracts only — dispatch/outbox wiring lands with the application
use cases in later ASSET phases. ``AssetEvents`` covers the events the finance
boundary map (`docs/refactor/assets_finance_boundary_map.md`) documents as the
integration points with Finance/Purchases/AP: Assets never calls
``finance_service.registrar_asiento`` or ``treasury_service.registrar_gasto_opex``
directly (see the ``test_assets_do_not_*`` architecture guardrails) — it
publishes these events and lets Finance decide.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class AssetEvents:
    # ── ciclo de vida del activo ────────────────────────────────────────────
    ASSET_REGISTERED = "ASSET_REGISTERED"
    ASSET_UPDATED = "ASSET_UPDATED"
    ASSET_COMMISSIONED = "ASSET_COMMISSIONED"
    ASSET_STATUS_CHANGED = "ASSET_STATUS_CHANGED"
    ASSET_CONDITION_CHANGED = "ASSET_CONDITION_CHANGED"

    # ── custodia (ASSET-4) ──────────────────────────────────────────────────
    ASSET_ASSIGNED = "ASSET_ASSIGNED"
    ASSET_RETURNED = "ASSET_RETURNED"
    ASSET_CUSTODIAN_CHANGED = "ASSET_CUSTODIAN_CHANGED"
    ASSET_LOCATION_CHANGED = "ASSET_LOCATION_CHANGED"

    # ── préstamos (ASSET-4, §21) ─────────────────────────────────────────────
    ASSET_LOANED = "ASSET_LOANED"
    ASSET_LOAN_RETURNED = "ASSET_LOAN_RETURNED"

    # ── transferencias (ASSET-5) ────────────────────────────────────────────
    ASSET_TRANSFER_REQUESTED = "ASSET_TRANSFER_REQUESTED"
    ASSET_TRANSFER_APPROVED = "ASSET_TRANSFER_APPROVED"
    ASSET_TRANSFER_PREPARED = "ASSET_TRANSFER_PREPARED"
    ASSET_TRANSFER_SHIPPED = "ASSET_TRANSFER_SHIPPED"
    ASSET_TRANSFER_RECEIVED = "ASSET_TRANSFER_RECEIVED"
    ASSET_TRANSFER_REJECTED = "ASSET_TRANSFER_REJECTED"
    ASSET_TRANSFER_CANCELLED = "ASSET_TRANSFER_CANCELLED"

    # ── mantenimiento (ASSET-6) ─────────────────────────────────────────────
    MAINTENANCE_PLAN_CREATED = "MAINTENANCE_PLAN_CREATED"
    MAINTENANCE_PLAN_UPDATED = "MAINTENANCE_PLAN_UPDATED"
    MAINTENANCE_WORK_ORDER_CREATED = "MAINTENANCE_WORK_ORDER_CREATED"
    MAINTENANCE_WORK_ORDER_APPROVED = "MAINTENANCE_WORK_ORDER_APPROVED"
    MAINTENANCE_WORK_ORDER_ASSIGNED = "MAINTENANCE_WORK_ORDER_ASSIGNED"
    MAINTENANCE_STARTED = "MAINTENANCE_STARTED"
    MAINTENANCE_PAUSED = "MAINTENANCE_PAUSED"
    MAINTENANCE_RESUMED = "MAINTENANCE_RESUMED"
    MAINTENANCE_COMPLETED = "MAINTENANCE_COMPLETED"
    MAINTENANCE_CLOSED = "MAINTENANCE_CLOSED"
    MAINTENANCE_CANCELLED = "MAINTENANCE_CANCELLED"
    MAINTENANCE_COST_CONFIRMED = "MAINTENANCE_COST_CONFIRMED"

    # ── inspecciones (ASSET-7) ──────────────────────────────────────────────
    ASSET_INSPECTION_CREATED = "ASSET_INSPECTION_CREATED"
    ASSET_INSPECTION_COMPLETED = "ASSET_INSPECTION_COMPLETED"
    ASSET_INSPECTION_FAILED = "ASSET_INSPECTION_FAILED"

    # ── medidores (ASSET-8, §39) ─────────────────────────────────────────────
    ASSET_METER_REGISTERED = "ASSET_METER_REGISTERED"
    ASSET_METER_READING_RECORDED = "ASSET_METER_READING_RECORDED"

    # ── documentación / garantías / seguros (ASSET-9, §40-43) ──────────────
    ASSET_DOCUMENT_UPLOADED = "ASSET_DOCUMENT_UPLOADED"
    ASSET_DOCUMENT_DELETED = "ASSET_DOCUMENT_DELETED"
    ASSET_WARRANTY_REGISTERED = "ASSET_WARRANTY_REGISTERED"
    ASSET_WARRANTY_EXPIRING = "ASSET_WARRANTY_EXPIRING"
    ASSET_WARRANTY_EXPIRED = "ASSET_WARRANTY_EXPIRED"
    ASSET_INSURANCE_REGISTERED = "ASSET_INSURANCE_REGISTERED"
    ASSET_INSURANCE_CANCELLED = "ASSET_INSURANCE_CANCELLED"

    # ── mejoras / capitalización propuesta (ASSET-10; Finanzas decide) ─────
    ASSET_IMPROVEMENT_COMPLETED = "ASSET_IMPROVEMENT_COMPLETED"
    ASSET_CAPITALIZATION_PROPOSED = "ASSET_CAPITALIZATION_PROPOSED"
    ASSET_CAPITALIZATION_UNDER_REVIEW = "ASSET_CAPITALIZATION_UNDER_REVIEW"
    ASSET_CAPITALIZATION_ACCEPTED = "ASSET_CAPITALIZATION_ACCEPTED"
    ASSET_CAPITALIZATION_REJECTED = "ASSET_CAPITALIZATION_REJECTED"
    ASSET_CAPITALIZATION_POSTED = "ASSET_CAPITALIZATION_POSTED"
    ASSET_CAPITALIZATION_CANCELLED = "ASSET_CAPITALIZATION_CANCELLED"

    # ── inventario físico (ASSET-11) ────────────────────────────────────────
    ASSET_PHYSICAL_INVENTORY_STARTED = "ASSET_PHYSICAL_INVENTORY_STARTED"
    ASSET_SCANNED = "ASSET_SCANNED"
    ASSET_DISCREPANCY_DETECTED = "ASSET_DISCREPANCY_DETECTED"
    ASSET_DISCREPANCY_RESOLVED = "ASSET_DISCREPANCY_RESOLVED"
    ASSET_PHYSICAL_INVENTORY_COMPLETED = "ASSET_PHYSICAL_INVENTORY_COMPLETED"
    ASSET_PHYSICAL_INVENTORY_CANCELLED = "ASSET_PHYSICAL_INVENTORY_CANCELLED"

    # ── baja (ASSET-12; Finanzas calcula ganancia/pérdida) ──────────────────
    ASSET_DISPOSAL_REQUESTED = "ASSET_DISPOSAL_REQUESTED"
    ASSET_DISPOSAL_UNDER_REVIEW = "ASSET_DISPOSAL_UNDER_REVIEW"
    ASSET_DISPOSAL_APPROVED = "ASSET_DISPOSAL_APPROVED"
    ASSET_DISPOSAL_REJECTED = "ASSET_DISPOSAL_REJECTED"
    ASSET_DISPOSAL_CANCELLED = "ASSET_DISPOSAL_CANCELLED"
    ASSET_DISPOSED = "ASSET_DISPOSED"

    # ── etiquetas / QR (ASSET-13, §49-51) ────────────────────────────────────
    ASSET_TAG_ISSUED = "ASSET_TAG_ISSUED"
    ASSET_TAG_PRINTED = "ASSET_TAG_PRINTED"
    ASSET_TAG_ACTIVATED = "ASSET_TAG_ACTIVATED"
    ASSET_TAG_REPLACED = "ASSET_TAG_REPLACED"
    ASSET_TAG_VOIDED = "ASSET_TAG_VOIDED"


ALL_ASSET_EVENTS = frozenset(
    v for k, v in vars(AssetEvents).items() if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(
    event_name: str,
    *,
    operation_id: str,
    asset_id: str,
    asset_number: str | None = None,
    branch_id: str | None = None,
    location_id: str | None = None,
    user_id: str | None = None,
    authorized_by: str | None = None,
    source_module: str = "assets",
    schema_version: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    **extra,
) -> dict:
    """Build a canonical event payload — one event_id per publish, operation_id
    threaded through for idempotency/audit correlation (§17, §87-88)."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "asset_id": asset_id,
        "asset_number": asset_number,
        "branch_id": branch_id,
        "location_id": location_id,
        "user_id": user_id,
        "authorized_by": authorized_by,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
        "schema_version": schema_version,
        "correlation_id": correlation_id or operation_id,
        "causation_id": causation_id,
    }
    payload.update(extra)
    return payload
