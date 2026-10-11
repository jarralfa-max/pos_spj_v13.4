"""ProductSettingsQuery (PROD-22, §45) — parámetros gobernados de Productos.

Se leen del catálogo gobernado (`backend/application/settings`), que versiona y
audita cada cambio. Aquí también se resuelven los destinatarios de las alertas:
roles → usuarios activos (canal interno) y la lista de teléfonos (WhatsApp).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.settings.configuration_reader import ConfigurationReader

DEFAULT_TYPE_KEY = "products.defaults.product_type"
DEFAULT_UNIT_KEY = "products.defaults.base_unit_code"
ALERTS_ENABLED_KEY = "products.alerts.enabled"
ALERT_ROLES_KEY = "products.alerts.recipient_roles"
WHATSAPP_ENABLED_KEY = "products.alerts.whatsapp_enabled"
WHATSAPP_PHONES_KEY = "products.alerts.whatsapp_phones"
REQUIRE_MEAT_CLASSIFICATION_KEY = "products.require.meat_classification"
REQUIRE_SHELF_LIFE_KEY = "products.require.shelf_life_for_perishables"
REQUIRE_QUALITY_PROFILE_KEY = "products.require.quality_profile_for_meat"
REQUIRE_CATCH_WEIGHT_RANGE_KEY = "products.require.catch_weight_range"
DEFAULT_YIELD_TOLERANCE_KEY = "products.yield.default_tolerance_pct"


def _split(raw) -> tuple[str, ...]:
    return tuple(p.strip() for p in str(raw or "").split(",") if p.strip())


@dataclass(frozen=True)
class ProductSettings:
    default_product_type: str
    default_base_unit_code: str
    alerts_enabled: bool
    alert_roles: tuple[str, ...]
    whatsapp_enabled: bool
    whatsapp_phones: tuple[str, ...]
    require_meat_classification: bool = False
    require_shelf_life: bool = False
    require_quality_profile: bool = False
    require_catch_weight_range: bool = False
    default_yield_tolerance_pct: str = "0"


class ProductSettingsQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def current(self) -> ProductSettings:
        reader = ConfigurationReader(self._conn)
        return ProductSettings(
            default_product_type=str(reader.get(DEFAULT_TYPE_KEY) or "RESALE_PRODUCT"),
            default_base_unit_code=str(reader.get(DEFAULT_UNIT_KEY) or "").upper(),
            alerts_enabled=bool(reader.get(ALERTS_ENABLED_KEY)),
            alert_roles=_split(reader.get(ALERT_ROLES_KEY)),
            whatsapp_enabled=bool(reader.get(WHATSAPP_ENABLED_KEY)),
            whatsapp_phones=_split(reader.get(WHATSAPP_PHONES_KEY)),
            require_meat_classification=bool(reader.get(REQUIRE_MEAT_CLASSIFICATION_KEY)),
            require_shelf_life=bool(reader.get(REQUIRE_SHELF_LIFE_KEY)),
            require_quality_profile=bool(reader.get(REQUIRE_QUALITY_PROFILE_KEY)),
            require_catch_weight_range=bool(reader.get(REQUIRE_CATCH_WEIGHT_RANGE_KEY)),
            default_yield_tolerance_pct=str(reader.get(DEFAULT_YIELD_TOLERANCE_KEY) or "0"))

    def alert_user_ids(self, settings: ProductSettings | None = None) -> list[str]:
        """Usuarios activos con alguno de los roles configurados."""
        settings = settings or self.current()
        roles = [r.lower() for r in settings.alert_roles]
        if not roles:
            return []
        try:
            rows = self._conn.execute(
                f"SELECT id FROM usuarios WHERE lower(trim(rol)) IN "
                f"({','.join('?' for _ in roles)}) AND COALESCE(activo, 1) = 1",
                roles).fetchall()
        except Exception:  # base sin tabla de usuarios: nadie a quien avisar
            return []
        return [r[0] for r in rows]
