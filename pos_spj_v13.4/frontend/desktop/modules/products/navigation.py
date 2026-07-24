"""Declarative navigation for the enterprise products module (§42, §52).

Pure data: the pages, their Spanish titles/tooltips, icon keys and the granular
PRODUCTS_* permission each requires. The app shell renders this and hides an entry
when the session lacks the permission (hiding is UX, not security — the backend
re-validates every action). Keeping it declarative makes the module map testable
without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.products.permissions import ProductPermissions


@dataclass(frozen=True)
class NavEntry:
    page_id: str
    title: str        # es-MX
    icon: str
    permission: str
    tooltip: str


PRODUCTS_NAV: tuple[NavEntry, ...] = (
    NavEntry("products_overview", "Resumen", "dashboard", ProductPermissions.VIEW,
             "Vista general: activos, cárnicos, internos, incompletos, recetas."),
    NavEntry("products_catalog", "Catálogo", "catalog", ProductPermissions.VIEW,
             "Catálogo maestro de productos con búsqueda y filtros."),
    NavEntry("products_meat", "Productos cárnicos", "meat", ProductPermissions.VIEW_MEAT,
             "Productos por especie, categoría, corte y perfil sanitario."),
    NavEntry("products_internal", "Productos internos", "internal",
             ProductPermissions.VIEW_INTERNAL,
             "WIP, semiterminados y productos de proceso no vendibles."),
    NavEntry("products_materials", "Materiales", "material", ProductPermissions.VIEW,
             "Materias primas, empaques, consumibles y MRO."),
    NavEntry("products_categories", "Categorías", "category", ProductPermissions.VIEW,
             "Categorías y marcas."),
    NavEntry("products_species", "Especies", "species", ProductPermissions.SPECIES_VIEW,
             "Catálogo de especies animales."),
    NavEntry("products_cuts", "Cortes", "cut", ProductPermissions.CUTS_VIEW,
             "Regiones anatómicas y clasificación jerárquica de cortes."),
    NavEntry("products_units", "Unidades", "unit", ProductPermissions.UNITS_VIEW,
             "Unidades de medida y conversiones."),
    NavEntry("products_barcodes", "Códigos", "barcode", ProductPermissions.BARCODES_MANAGE,
             "Códigos de barras, PLU, báscula y códigos alternos."),
    NavEntry("products_branches", "Sucursales y surtidos", "branch",
             ProductPermissions.BRANCH_ASSIGNMENT_VIEW,
             "Habilitación por sucursal y surtidos por canal."),
    NavEntry("products_recipes", "Recetas", "recipe", ProductPermissions.RECIPE_VIEW,
             "Recetas y BOM versionadas (venta, producción, procesamiento)."),
    NavEntry("products_yields", "Rendimientos", "yield", ProductPermissions.YIELD_VIEW,
             "Perfiles de rendimiento multi-especie con tolerancia."),
    NavEntry("products_cutting", "Esquemas de despiece", "cutting",
             ProductPermissions.CUTTING_SCHEME_VIEW,
             "Esquemas de despiece por especie y nivel."),
    NavEntry("products_bundles", "Combos y paquetes", "bundle", ProductPermissions.VIEW,
             "Combos virtuales, kits armados, cajas y sets."),
    NavEntry("products_external", "Catálogo externo", "external",
             ProductPermissions.EXTERNAL_SEARCH,
             "Búsqueda y revisión de catálogos externos (Open Food Facts, proveedor, CSV)."),
    NavEntry("products_imports", "Importaciones", "import", ProductPermissions.IMPORT_EXECUTE,
             "Lotes de importación y su estado."),
    NavEntry("products_data_quality", "Calidad de datos", "quality", ProductPermissions.VIEW,
             "Score de calidad y productos incompletos."),
    NavEntry("products_notifications", "Notificaciones", "bell",
             ProductPermissions.NOTIFICATIONS_MANAGE,
             "Reglas de notificación y alertas de WhatsApp."),
    NavEntry("products_audit", "Auditoría", "audit", ProductPermissions.VIEW_AUDIT,
             "Bitácora de cambios del maestro de productos."),
    NavEntry("products_settings", "Configuración", "settings",
             ProductPermissions.SETTINGS_VIEW,
             "Parámetros del módulo de productos."),
)


def visible_entries(has_permission) -> tuple[NavEntry, ...]:
    """Entries the session may see. ``has_permission(code) -> bool``."""
    return tuple(e for e in PRODUCTS_NAV if has_permission(e.permission))
