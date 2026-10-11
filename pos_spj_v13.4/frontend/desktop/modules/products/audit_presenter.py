"""Presenter de la bitácora de Productos (PROD-22, §40).

Traduce las acciones técnicas a es-MX y resume el antes/después para la tabla.
Consultar exige `PRODUCTOS.ver.auditoria`; sin él no se lee nada.
"""

from __future__ import annotations

import json

from backend.application.products.permissions import ProductPermissions

ACTION_ES = {
    "PRODUCT_CREATED": "Alta de producto", "PRODUCT_UPDATED": "Edición de producto",
    "PRODUCT_SUBMITTED": "Enviado a revisión", "PRODUCT_APPROVED": "Aprobado",
    "PRODUCT_ACTIVATED": "Activado", "PRODUCT_BLOCKED": "Bloqueado",
    "PRODUCT_DEACTIVATED": "Desactivado", "PRODUCT_DISCONTINUED": "Descontinuado",
    "CODE_OVERRIDE": "Código capturado a mano",
    "PRODUCT_IMAGE_ADDED": "Imagen agregada", "PRODUCT_IMAGE_REMOVED": "Imagen eliminada",
    "PRODUCT_IMAGE_PRIMARY_SET": "Imagen principal",
    "PRODUCT_IMAGE_BACKGROUND_REMOVED": "Fondo quitado",
    "PRODUCT_IMAGE_BACKGROUND_RESTORED": "Fondo restaurado",
    "PRODUCT_BARCODE_ASSIGNED": "Código de barras asignado",
    "PRODUCT_BARCODE_UPDATED": "Código de barras actualizado",
    "PRODUCT_ALTERNATE_CODE_ADDED": "Código alterno agregado",
    "PRODUCT_SHELF_LIFE_PROFILE_SET": "Vida útil", "PRODUCT_QUALITY_PROFILE_SET": "Perfil de calidad",
    "PRODUCT_LOGISTICS_PROFILE_SET": "Perfil logístico",
    "PRODUCT_CATCH_WEIGHT_CONFIGURED": "Peso variable",
    "PRODUCT_INTERNAL_STAGE_CHANGED": "Etapa interna",
    "BRANCH_PRODUCT_ENABLED": "Habilitado en sucursal",
    "BRANCH_PRODUCT_DISABLED": "Deshabilitado en sucursal",
    "ASSORTMENT_CREATED": "Surtido creado", "ASSORTMENT_PRODUCT_ENABLED": "En surtido",
    "UNIT_CREATED": "Unidad creada", "UNIT_UPDATED": "Unidad editada",
    "UNIT_CONVERSION_CREATED": "Conversión creada", "UNIT_CONVERSION_UPDATED": "Conversión editada",
    "SPECIES_CREATED": "Especie creada", "ANATOMICAL_REGION_CREATED": "Región anatómica creada",
    "CUT_CLASSIFICATION_CREATED": "Corte creado",
    "PRODUCT_RECIPE_CREATED": "Receta creada", "RECIPE_VERSION_UPDATED": "Receta editada",
    "PRODUCT_YIELD_PROFILE_CREATED": "Rendimiento creado",
    "YIELD_VERSION_UPDATED": "Rendimiento editado",
    "YIELD_VERSION_SUBMITTED": "Rendimiento enviado a revisión",
    "YIELD_VERSION_APPROVED": "Rendimiento aprobado",
    "PRODUCT_CUTTING_SCHEME_CREATED": "Despiece creado",
    "CUTTING_VERSION_UPDATED": "Despiece editado",
    "CUTTING_SCHEME_REVERSE_RECONSTRUCTION_CHANGED": "Armado por partes",
    "PRODUCT_BUNDLE_CREATED": "Combo creado", "BUNDLE_VERSION_UPDATED": "Combo editado",
    "PRODUCT_IMPORT_BATCH_CREATED": "Importación cargada",
    "PRODUCT_IMPORT_BATCH_APPROVED": "Importación aprobada",
    "PRODUCT_IMPORT_BATCH_EXECUTED": "Importación ejecutada",
    "EXTERNAL_CATALOG_SEARCHED": "Búsqueda externa",
    "EXTERNAL_RECORD_IMPORTED": "Registro externo importado",
    "EXTERNAL_RECORD_REJECTED": "Registro externo rechazado",
    "EXTERNAL_PRODUCT_IMPORT_APPROVED": "Importación externa aprobada",
}


def action_label(action: str) -> str:
    return ACTION_ES.get(action, action.replace("_", " ").capitalize())


def summarize(value) -> str:
    """Una línea legible del antes/después (el detalle completo, en la ficha)."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
    return str(value)


class ProductAuditPresenter:
    def __init__(self, *, read_factory, has_permission=None) -> None:
        self._read = read_factory
        self._has = has_permission

    @property
    def can_view(self) -> bool:
        return True if self._has is None else bool(self._has(ProductPermissions.VIEW_AUDIT))

    def action_options(self) -> list[tuple[str, str]]:
        if not self.can_view:
            return []
        return [(a, action_label(a)) for a in self._read().actions()]

    def entries(self, *, text: str | None = None, action: str | None = None) -> list[dict]:
        if not self.can_view:
            return []
        rows = self._read().list_entries(text=text, action=action)
        for row in rows:
            row["action_label"] = action_label(row["action"])
            row["subject"] = (f"{row['product_code']} · {row['product_name']}"
                              if row.get("product_name") else row.get("entity_id") or "")
            row["detail"] = json.dumps({"antes": row["before"], "despues": row["after"]},
                                       ensure_ascii=False, indent=2, default=str)
            row["change"] = summarize(row["after"]) or summarize(row["before"])
        return rows
