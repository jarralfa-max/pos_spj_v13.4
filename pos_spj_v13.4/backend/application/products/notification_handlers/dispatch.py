"""dispatch_product_alerts (PROD-16, §35) — the first real trigger point for
`detect_product_alerts`.

Before this existed, `detect_product_alerts`/`ProductNotificationService`
were fully built and unit-tested but had zero production call sites
(confirmed by grep before writing this) — a complete, tested library nobody
called. This is intentionally OPTIONAL and additive: every caller (currently
`CreateProductMasterUseCase`/`UpdateProductMasterUseCase`) only dispatches
when both `notification_service` and `notify_recipients` are explicitly
provided, so existing callers/tests that construct these use cases without
them (the overwhelming majority, today) see zero behavior change. Recipient
resolution (who should receive product alerts) is deliberately left to the
caller — no role-based subscription system exists yet for Products, out of
scope for this phase.
"""

from __future__ import annotations

from backend.domain.products.notification_enums import NotificationChannel

from backend.application.products.notification_handlers.product_alert_detectors import (
    detect_product_alerts,
)
from backend.application.products.notifications.notification_service import (
    ProductNotificationService,
)
from backend.domain.products.entities.product import Product
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.repositories.products.unit_repository import (
    UnitRepository,
)

_MESSAGES = {
    "PRODUCT_INCOMPLETE": "El producto {code} tiene datos maestros incompletos.",
    "MEAT_WITHOUT_SPECIES": "El producto cárnico {code} no tiene especie asignada.",
    "PERISHABLE_WITHOUT_SHELF_LIFE":
        "El producto perecedero {code} no tiene perfil de vida útil.",
    "CATCH_WEIGHT_WITHOUT_RANGE":
        "El producto de peso variable {code} no tiene rango de peso configurado.",
    "LOT_REQUIRED_NOT_CONFIGURED": "El producto {code} requiere lote y no está configurado.",
    "MEAT_WITHOUT_QUALITY_PROFILE":
        "El producto cárnico {code} no tiene perfil de calidad.",
    "PENDING_APPROVAL": "El producto {code} está pendiente de aprobación.",
}


def dispatch_product_alerts(
    conn,
    product: Product,
    *,
    notification_service: ProductNotificationService | None,
    notify_recipients: list[str] | None,
    operation_id: str,
    whatsapp_recipients: list[str] | None = None,
) -> None:
    """No-ops unless both `notification_service` and `notify_recipients` are
    given — see module docstring."""
    if notification_service is None or not (notify_recipients or whatsapp_recipients):
        return
    profiles = ProfileRepository(conn)
    units = UnitRepository(conn)
    alerts = detect_product_alerts(
        product,
        has_shelf_life_profile=profiles.has_shelf_life(product.id),
        has_quality_profile=profiles.get_quality(product.id) is not None,
        # PROD-22: «configurado» exige rango; una fila deshabilitada o sin
        # mínimo/máximo no apaga la alerta de peso variable sin rango.
        catch_weight_configured=_catch_weight_has_range(units.get_catch_weight(product.id)),
    )
    for alert_type in alerts:
        message = _MESSAGES.get(alert_type.value, alert_type.value).format(
            code=product.code.value)
        if notify_recipients:  # campana: ids de usuario, nunca WhatsApp
            notification_service.notify(
                alert_type, entity_id=product.id, message=message,
                recipients=notify_recipients, operation_id=operation_id,
                only_channels={NotificationChannel.IN_APP})
        if whatsapp_recipients:  # WhatsApp: teléfonos, sólo alertas de alto impacto
            notification_service.notify(
                alert_type, entity_id=product.id, message=message,
                recipients=whatsapp_recipients, operation_id=operation_id,
                only_channels={NotificationChannel.WHATSAPP})


def _catch_weight_has_range(cfg) -> bool:
    return bool(cfg is not None and cfg.enabled and cfg.maximum_weight
                and cfg.maximum_weight > 0)
