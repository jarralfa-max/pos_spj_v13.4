"""Editar los parámetros de Productos (PROD-22, §45) — Productos → Configuración.

Cada grupo exige su permiso (§38): valores por omisión → `configuracion.editar`;
alertas → `notificacion.gestionar`; WhatsApp → `whatsapp.gestionar`. Se guarda
por `GovernedSettingsWriter` (una versión nueva auditada por valor que cambia) y
se deja rastro en la bitácora de Productos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
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
    ProductSettingsQuery,
)
from backend.application.security.unwired_policy import unwired
from backend.application.settings.governance import GovernedSettingsWriter
from backend.domain.settings.exceptions import ConfigurationDomainError

logger = logging.getLogger("spj.products.settings_use_cases")

#: clave → permiso que la gobierna
_PERMISSION = {
    DEFAULT_TYPE_KEY: ProductPermissions.SETTINGS_MANAGE,
    DEFAULT_UNIT_KEY: ProductPermissions.SETTINGS_MANAGE,
    DEFAULT_YIELD_TOLERANCE_KEY: ProductPermissions.SETTINGS_MANAGE,
    REQUIRE_MEAT_CLASSIFICATION_KEY: ProductPermissions.SETTINGS_MANAGE,
    REQUIRE_SHELF_LIFE_KEY: ProductPermissions.SETTINGS_MANAGE,
    REQUIRE_QUALITY_PROFILE_KEY: ProductPermissions.SETTINGS_MANAGE,
    REQUIRE_CATCH_WEIGHT_RANGE_KEY: ProductPermissions.SETTINGS_MANAGE,
    ALERTS_ENABLED_KEY: ProductPermissions.NOTIFICATIONS_MANAGE,
    ALERT_ROLES_KEY: ProductPermissions.NOTIFICATIONS_MANAGE,
    WHATSAPP_ENABLED_KEY: ProductPermissions.WHATSAPP_ALERTS_MANAGE,
    WHATSAPP_PHONES_KEY: ProductPermissions.WHATSAPP_ALERTS_MANAGE,
}


@dataclass(frozen=True)
class SettingsResult:
    success: bool
    changed: tuple[str, ...]
    message: str


class UpdateProductSettingsUseCase:
    name = "UpdateProductSettingsUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or unwired(ProductsAuthorizationPolicy)

    def execute(self, *, changes: dict, user_id: str | None, operation_id: str,
                reason: str = "Productos → Configuración") -> SettingsResult:
        unknown = [k for k in changes if k not in _PERMISSION]
        if unknown:
            return SettingsResult(False, (), f"Parámetro desconocido: {', '.join(unknown)}")
        for key in changes:
            self._auth.require(user_id or "", _PERMISSION[key])
        clean = dict(changes)
        if DEFAULT_UNIT_KEY in clean:
            clean[DEFAULT_UNIT_KEY] = str(clean[DEFAULT_UNIT_KEY] or "").strip().upper()
        for key in (ALERT_ROLES_KEY, WHATSAPP_PHONES_KEY):
            if key in clean:
                clean[key] = ",".join(p.strip() for p in str(clean[key] or "").split(",")
                                      if p.strip())
        if clean.get(WHATSAPP_ENABLED_KEY) and not (
                clean.get(WHATSAPP_PHONES_KEY)
                or ProductSettingsQuery(self._conn).current().whatsapp_phones):
            return SettingsResult(False, (), "Para enviar por WhatsApp captura al menos un teléfono")
        before = ProductSettingsQuery(self._conn).current()
        writer = GovernedSettingsWriter(self._conn)
        try:
            changed = writer.stage(clean, actor_user_id=user_id or "", reason=reason,
                                   operation_id=operation_id)
            if changed:
                record_product_audit_entry(
                    self._conn, action="PRODUCT_SETTINGS_UPDATED", entity_id="products.settings",
                    user_id=user_id or "", operation_id=operation_id,
                    before={k: str(getattr(before, _FIELD[k])) for k in changed},
                    after={k: ("***" if k == WHATSAPP_PHONES_KEY else str(clean[k]))
                           for k in changed},
                    reason=reason)
            self._conn.commit()
        except ConfigurationDomainError as exc:
            self._rollback()
            return SettingsResult(False, (), str(exc))
        except Exception:
            self._rollback()
            logger.exception("update product settings failed op=%s", operation_id)
            raise
        writer.publish()
        return SettingsResult(True, changed,
                              "Configuración guardada." if changed else "No hubo cambios.")

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


_FIELD = {
    DEFAULT_TYPE_KEY: "default_product_type", DEFAULT_UNIT_KEY: "default_base_unit_code",
    ALERTS_ENABLED_KEY: "alerts_enabled", ALERT_ROLES_KEY: "alert_roles",
    WHATSAPP_ENABLED_KEY: "whatsapp_enabled", WHATSAPP_PHONES_KEY: "whatsapp_phones",
    DEFAULT_YIELD_TOLERANCE_KEY: "default_yield_tolerance_pct",
    REQUIRE_MEAT_CLASSIFICATION_KEY: "require_meat_classification",
    REQUIRE_SHELF_LIFE_KEY: "require_shelf_life",
    REQUIRE_QUALITY_PROFILE_KEY: "require_quality_profile",
    REQUIRE_CATCH_WEIGHT_RANGE_KEY: "require_catch_weight_range",
}
