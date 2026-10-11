"""Presenter de Productos → Configuración y Notificaciones (PROD-22, §35/§36/§45)."""

from __future__ import annotations

import logging

from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_settings_query import (
    ALERT_ROLES_KEY,
    ALERTS_ENABLED_KEY,
    DEFAULT_TYPE_KEY,
    DEFAULT_UNIT_KEY,
    DEFAULT_YIELD_TOLERANCE_KEY,
    REQUIRE_CATCH_WEIGHT_RANGE_KEY,
    REQUIRE_MEAT_CLASSIFICATION_KEY,
    REQUIRE_QUALITY_PROFILE_KEY,
    REQUIRE_SHELF_LIFE_KEY,
    WHATSAPP_ENABLED_KEY,
    WHATSAPP_PHONES_KEY,
)

logger = logging.getLogger("spj.products.settings_presenter")

CHANNEL_ES = {"IN_APP": "Campana", "WHATSAPP": "WhatsApp"}
SEVERITY_ES = {"INFO": "Informativa", "WARNING": "Advertencia", "DANGER": "Grave",
               "CRITICAL": "Crítica"}
STATUS_ES = {"SENT": "Enviada", "THROTTLED": "Omitida (repetida)", "FAILED": "Falló"}
OUTBOX_STATUS_ES = {"PENDING": "En cola", "SENT": "Entregada al servicio",
                    "FAILED": "Falló (sin más reintentos)"}


class ProductSettingsPresenter:
    def __init__(self, *, read_factory, write_factory=None, log_factory=None,
                 has_permission=None, session=None, outbox_factory=None,
                 retry_factory=None) -> None:
        self._read = read_factory
        self._write = write_factory
        self._log = log_factory
        self._outbox = outbox_factory
        self._retry = retry_factory
        self._has = has_permission
        self._session = session

    def _allowed(self, code: str) -> bool:
        if self._write is None:
            return False
        return True if self._has is None else bool(self._has(code))

    @property
    def can_view(self) -> bool:
        return True if self._has is None else bool(self._has(ProductPermissions.SETTINGS_VIEW))

    @property
    def can_edit_defaults(self) -> bool:
        return self._allowed(ProductPermissions.SETTINGS_MANAGE)

    @property
    def can_edit_alerts(self) -> bool:
        return self._allowed(ProductPermissions.NOTIFICATIONS_MANAGE)

    @property
    def can_edit_whatsapp(self) -> bool:
        return self._allowed(ProductPermissions.WHATSAPP_ALERTS_MANAGE)

    def current(self):
        return self._read().current()

    def defaults(self) -> dict:
        """Lo que la ficha usa al dar de alta un producto."""
        try:
            s = self._read().current()
        except Exception:  # sin catálogo de ajustes: la ficha sin preselección
            logger.exception("No se pudieron leer los valores por omisión de Productos")
            return {}
        return {"product_type": s.default_product_type,
                "base_unit_code": s.default_base_unit_code,
                "yield_tolerance_pct": s.default_yield_tolerance_pct}

    def save(self, *, defaults: dict | None = None, alerts: dict | None = None,
             whatsapp: dict | None = None,
             requirements: dict | None = None) -> tuple[bool, str]:
        if self._write is None:
            return False, "Sin permisos para cambiar la configuración"
        changes: dict = {}
        if defaults is not None:
            changes[DEFAULT_TYPE_KEY] = defaults.get("product_type")
            changes[DEFAULT_UNIT_KEY] = defaults.get("base_unit_code") or ""
        if defaults is not None and "yield_tolerance_pct" in defaults:
            changes[DEFAULT_YIELD_TOLERANCE_KEY] = str(defaults["yield_tolerance_pct"] or "0")
        if requirements is not None:
            changes[REQUIRE_MEAT_CLASSIFICATION_KEY] = bool(requirements.get("meat_classification"))
            changes[REQUIRE_SHELF_LIFE_KEY] = bool(requirements.get("shelf_life"))
            changes[REQUIRE_QUALITY_PROFILE_KEY] = bool(requirements.get("quality_profile"))
            changes[REQUIRE_CATCH_WEIGHT_RANGE_KEY] = bool(requirements.get("catch_weight_range"))
        if alerts is not None:
            changes[ALERTS_ENABLED_KEY] = bool(alerts.get("enabled"))
            changes[ALERT_ROLES_KEY] = alerts.get("roles") or ""
        if whatsapp is not None:
            changes[WHATSAPP_ENABLED_KEY] = bool(whatsapp.get("enabled"))
            changes[WHATSAPP_PHONES_KEY] = whatsapp.get("phones") or ""
        from backend.shared.ids import new_uuid
        try:
            result = self._write().execute(changes=changes, operation_id=new_uuid(),
                                           user_id=getattr(self._session, "user_id", None))
        except Exception as exc:  # noqa: BLE001 — permiso o validación: a la pantalla
            logger.exception("Guardar configuración de Productos falló")
            return False, f"Error: {exc}"
        return result.success, result.message

    def notification_log(self, limit: int = 300) -> list[dict]:
        if self._log is None or not self.can_view:
            return []
        return self._log().recent(limit=limit)

    def whatsapp_queue(self) -> list[dict]:
        if self._outbox is None or not self.can_view:
            return []
        return self._outbox().recent()

    def retry_whatsapp(self, message_id: str) -> tuple[bool, str]:
        if self._retry is None:
            return False, "Sin permisos para reintentar"
        from backend.shared.ids import new_uuid
        try:
            return self._retry().execute(message_id=message_id, operation_id=new_uuid(),
                                         user_id=getattr(self._session, "user_id", None))
        except Exception as exc:  # noqa: BLE001 — permiso: a la pantalla
            logger.exception("Reintentar WhatsApp falló")
            return False, f"Error: {exc}"
