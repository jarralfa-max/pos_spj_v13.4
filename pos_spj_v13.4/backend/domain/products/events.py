"""Canonical product events (§46).

All product domain events are published post-commit with a minimum payload:
distinct event_id / operation_id / entity_id plus product/user/branch context.
These replace the legacy ad-hoc Spanish signals (PRODUCTO_CREADO, PRODUCTO_
ACTUALIZADO, RECETA_CREADA, …). Meat/recipe/yield/cutting/bundle/external events
are added by their phases (PROD-3, PROD-9…PROD-15).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class ProductEvents:
    # ── ciclo de vida del producto (§46) ──────────────────────────────────
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_UPDATED = "PRODUCT_UPDATED"
    PRODUCT_SUBMITTED = "PRODUCT_SUBMITTED"
    PRODUCT_APPROVED = "PRODUCT_APPROVED"
    PRODUCT_ACTIVATED = "PRODUCT_ACTIVATED"
    PRODUCT_BLOCKED = "PRODUCT_BLOCKED"
    PRODUCT_DEACTIVATED = "PRODUCT_DEACTIVATED"
    PRODUCT_DISCONTINUED = "PRODUCT_DISCONTINUED"

    # ── clasificación / variantes / códigos (PROD-3, PROD-5, PROD-7) ──────
    MEAT_PRODUCT_CLASSIFIED = "MEAT_PRODUCT_CLASSIFIED"
    MEAT_PRODUCT_CLASSIFICATION_CHANGED = "MEAT_PRODUCT_CLASSIFICATION_CHANGED"
    PRODUCT_VARIANT_CREATED = "PRODUCT_VARIANT_CREATED"
    PRODUCT_BARCODE_ASSIGNED = "PRODUCT_BARCODE_ASSIGNED"
    PRODUCT_UNIT_CONVERSION_UPDATED = "PRODUCT_UNIT_CONVERSION_UPDATED"
    PRODUCT_BRANCH_ASSIGNMENT_UPDATED = "PRODUCT_BRANCH_ASSIGNMENT_UPDATED"

    # ── recetas / rendimientos / despiece (PROD-9…11) ─────────────────────
    PRODUCT_RECIPE_CREATED = "PRODUCT_RECIPE_CREATED"
    PRODUCT_RECIPE_VERSION_CREATED = "PRODUCT_RECIPE_VERSION_CREATED"
    PRODUCT_RECIPE_VERSION_APPROVED = "PRODUCT_RECIPE_VERSION_APPROVED"
    PRODUCT_RECIPE_VERSION_ACTIVATED = "PRODUCT_RECIPE_VERSION_ACTIVATED"
    PRODUCT_YIELD_PROFILE_CREATED = "PRODUCT_YIELD_PROFILE_CREATED"
    PRODUCT_YIELD_VERSION_APPROVED = "PRODUCT_YIELD_VERSION_APPROVED"
    PRODUCT_YIELD_VERSION_ACTIVATED = "PRODUCT_YIELD_VERSION_ACTIVATED"
    PRODUCT_CUTTING_SCHEME_CREATED = "PRODUCT_CUTTING_SCHEME_CREATED"
    PRODUCT_CUTTING_SCHEME_ACTIVATED = "PRODUCT_CUTTING_SCHEME_ACTIVATED"

    # ── internos / externos / calidad de datos (PROD-6, PROD-15) ──────────
    PRODUCT_INTERNAL_CREATED = "PRODUCT_INTERNAL_CREATED"
    EXTERNAL_PRODUCT_MATCH_DETECTED = "EXTERNAL_PRODUCT_MATCH_DETECTED"
    EXTERNAL_PRODUCT_IMPORT_APPROVED = "EXTERNAL_PRODUCT_IMPORT_APPROVED"
    PRODUCT_DATA_QUALITY_CHANGED = "PRODUCT_DATA_QUALITY_CHANGED"

    # ── notificaciones (PROD-16) ──────────────────────────────────────────
    PRODUCT_NOTIFICATION_CREATED = "PRODUCT_NOTIFICATION_CREATED"
    PRODUCT_WHATSAPP_ALERT_SENT = "PRODUCT_WHATSAPP_ALERT_SENT"

    # ── integración con Calidad (PROD-17, §34) ────────────────────────────
    PRODUCT_QUALITY_BLOCKED = "PRODUCT_QUALITY_BLOCKED"
    PRODUCT_QUALITY_RELEASED = "PRODUCT_QUALITY_RELEASED"


ALL_PRODUCT_EVENTS = frozenset(
    v for k, v in vars(ProductEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_product_event_payload(
    event_name: str,
    *,
    operation_id: str,
    entity_id: str,
    product_id: str | None = None,
    product_type: str | None = None,
    lifecycle_status: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
    source_module: str = "products",
    **extra,
) -> dict:
    if event_name not in ALL_PRODUCT_EVENTS:
        raise ValueError(f"Evento de producto desconocido: {event_name}")
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "product_id": product_id,
        "product_type": product_type,
        "lifecycle_status": lifecycle_status,
        "branch_id": branch_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload
