"""Product notification policy (§35, §36) — severity + channels + recipients.

Maps each alert type to its severity and the channels it should reach. WhatsApp is
reserved for high-impact alerts only (§36): quality-blocked products, critical
recipes without an active version, out-of-tolerance yields, meat products without a
sanitary/quality profile, critical duplicate barcodes, failed mass imports and
discontinued-but-active strategic products.
"""

from __future__ import annotations

from backend.domain.products.notification_enums import (
    NotificationChannel,
    NotificationSeverity,
    ProductAlertType,
)

_SEVERITY: dict[ProductAlertType, NotificationSeverity] = {
    ProductAlertType.PRODUCT_INCOMPLETE: NotificationSeverity.WARNING,
    ProductAlertType.PENDING_APPROVAL: NotificationSeverity.INFO,
    ProductAlertType.BARCODE_DUPLICATE: NotificationSeverity.DANGER,
    ProductAlertType.CONVERSION_INCONSISTENT: NotificationSeverity.WARNING,
    ProductAlertType.RECIPE_CIRCULAR: NotificationSeverity.CRITICAL,
    ProductAlertType.YIELD_OUT_OF_TOLERANCE: NotificationSeverity.DANGER,
    ProductAlertType.YIELD_PROFILE_UNAPPROVED: NotificationSeverity.WARNING,
    ProductAlertType.MEAT_WITHOUT_SPECIES: NotificationSeverity.DANGER,
    ProductAlertType.PERISHABLE_WITHOUT_SHELF_LIFE: NotificationSeverity.WARNING,
    ProductAlertType.LOT_REQUIRED_NOT_CONFIGURED: NotificationSeverity.WARNING,
    ProductAlertType.CATCH_WEIGHT_WITHOUT_RANGE: NotificationSeverity.WARNING,
    ProductAlertType.MEAT_WITHOUT_QUALITY_PROFILE: NotificationSeverity.DANGER,
    ProductAlertType.RECIPE_VERSION_EXPIRING: NotificationSeverity.INFO,
    ProductAlertType.DISCONTINUED_STILL_ACTIVE: NotificationSeverity.WARNING,
    ProductAlertType.EXTERNAL_DATA_CONFLICT: NotificationSeverity.WARNING,
    ProductAlertType.IMPORT_WITH_ERRORS: NotificationSeverity.DANGER,
    ProductAlertType.QUALITY_BLOCKED: NotificationSeverity.CRITICAL,
}

# Alertas de alto impacto que además salen por WhatsApp (§36).
_WHATSAPP_ALERTS = frozenset({
    ProductAlertType.QUALITY_BLOCKED,
    ProductAlertType.RECIPE_CIRCULAR,
    ProductAlertType.YIELD_OUT_OF_TOLERANCE,
    ProductAlertType.MEAT_WITHOUT_QUALITY_PROFILE,
    ProductAlertType.BARCODE_DUPLICATE,
    ProductAlertType.IMPORT_WITH_ERRORS,
    ProductAlertType.DISCONTINUED_STILL_ACTIVE,
})


def severity_for(alert_type: ProductAlertType) -> NotificationSeverity:
    return _SEVERITY.get(alert_type, NotificationSeverity.INFO)


def channels_for(
    alert_type: ProductAlertType, *, whatsapp_enabled: bool = True
) -> tuple[NotificationChannel, ...]:
    channels = [NotificationChannel.IN_APP]
    if whatsapp_enabled and alert_type in _WHATSAPP_ALERTS:
        channels.append(NotificationChannel.WHATSAPP)
    return tuple(channels)


def is_high_impact(alert_type: ProductAlertType) -> bool:
    return alert_type in _WHATSAPP_ALERTS
