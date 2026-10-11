"""ProductActivationReadinessQueryService (P0-05) — faltantes antes de activar.

La UI muestra la lista de datos maestros faltantes antes de permitir "Activar". Usa
los invariantes de la entidad `Product` (`missing_activation_data`) más reglas de
capacidad (vendible/interno) para explicar por qué un producto no puede activarse.
Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.enums import MEAT_PRODUCT_TYPES, ProductType


@dataclass(frozen=True)
class ActivationReadiness:
    ready: bool
    missing: list[str] = field(default_factory=list)


_LABELS = {
    "base_unit_id": "Unidad base",
    "category_id": "Categoría",
    "species_id": "Especie (producto cárnico)",
    "sellable_unit": "Unidad válida para venta",
    "internal_conflict": "Interno no puede ser vendible",
    # Exigencias configurables (Productos → Configuración, «sólo endurecer»).
    "meat_classification": "Clasificación cárnica (categoría o corte)",
    "shelf_life": "Vida útil (controla caducidad o es perecedero)",
    "quality_profile": "Perfil de calidad (producto cárnico)",
    "catch_weight_range": "Rango de peso variable",
}


def _exists(conn, sql: str, product_id: str) -> bool:
    try:
        return conn.execute(sql, (product_id,)).fetchone() is not None
    except Exception:  # tabla ausente en bases reducidas: el dato no existe
        return False


class ProductActivationReadinessQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def readiness(self, product_id: str) -> ActivationReadiness:
        row = self._conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            return ActivationReadiness(False, ["El producto no existe"])
        r = dict(row)
        missing: list[str] = []
        if not r.get("base_unit_id"):
            missing.append(_LABELS["base_unit_id"])
        if not r.get("category_id"):
            missing.append(_LABELS["category_id"])
        is_meat = ProductType(r["product_type"]) in MEAT_PRODUCT_TYPES
        if is_meat and not r.get("species_id"):
            missing.append(_LABELS["species_id"])
        if r.get("internal_only") and r.get("sellable"):
            missing.append(_LABELS["internal_conflict"])
        missing.extend(self._configured_requirements(r, is_meat))
        return ActivationReadiness(ready=not missing, missing=missing)

    def _configured_requirements(self, r: dict, is_meat: bool) -> list[str]:
        """PROD-22: exigencias ADICIONALES encendidas en Productos → Configuración.
        Apagadas por omisión. Es la misma regla que el caso de uso de activación
        revalida en el backend (la pantalla sólo la explica)."""
        try:
            from backend.application.products.queries.product_settings_query import (
                ProductSettingsQuery,
            )
            s = ProductSettingsQuery(self._conn).current()
        except Exception:  # sin catálogo de ajustes: sin exigencias adicionales
            return []
        pid, c, missing = r["id"], self._conn, []
        if s.require_meat_classification and is_meat and not _exists(
                c, "SELECT 1 FROM product_meat_classifications WHERE product_id=? "
                   "AND (meat_category IS NOT NULL OR cut_classification_id IS NOT NULL)", pid):
            missing.append(_LABELS["meat_classification"])
        perishable = bool(r.get("expiration_controlled")) or _exists(
            c, "SELECT 1 FROM product_logistics_profiles WHERE product_id=? AND perishable=1", pid)
        if s.require_shelf_life and perishable and not _exists(
                c, "SELECT 1 FROM product_shelf_life_profiles WHERE product_id=?", pid):
            missing.append(_LABELS["shelf_life"])
        if s.require_quality_profile and is_meat and not _exists(
                c, "SELECT 1 FROM product_quality_profiles WHERE product_id=?", pid):
            missing.append(_LABELS["quality_profile"])
        if s.require_catch_weight_range and r.get("catch_weight_enabled") and not _exists(
                c, "SELECT 1 FROM product_catch_weight_config WHERE product_id=? AND enabled=1 "
                   "AND COALESCE(minimum_weight,'')<>'' AND COALESCE(maximum_weight,'')<>''", pid):
            missing.append(_LABELS["catch_weight_range"])
        return missing
