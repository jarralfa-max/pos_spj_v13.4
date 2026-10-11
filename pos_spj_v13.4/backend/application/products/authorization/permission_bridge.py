"""Puente de permisos Productos legacy → canónico (PROD-19 paso 8).

El catálogo vivo de la app usa permisos módulo-nivel en español (`PRODUCTOS.ver`,
`PRODUCTOS.crear`, …) y los permisos gruesos legacy (`CREAR_PRODUCTO`, …). El
contexto canónico de Productos define permisos granulares en inglés
(`ProductPermissions.*` = `PRODUCTS_*`).

Este puente mapea cada permiso canónico a los códigos legacy que lo conceden, y
construye un verificador `has(codigo_canonico) -> bool` sobre la sesión viva. Es
**aditivo**: no cambia el catálogo ni el gating del menú (sin riesgo de lock-out);
permite que la UI enterprise razone en términos canónicos mientras los roles siguen
sembrados con `PRODUCTOS.accion`. Un rol que ya tenga el código canónico en inglés
también funciona.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.products.permissions import ProductPermissions

#: Permiso canónico → códigos gruesos que lo conceden (cualquiera basta).
#:
#: Re-auditoría PROD-22 (2026-10-09), medido en la base real: NINGÚN rol tenía
#: sembrado un solo permiso granular de Productos, así que todo se decidía aquí.
#: Y aquí había dos huecos: (1) aprobar/activar se concedían con
#: ``PRODUCTOS.editar`` — quien captura podía aprobar y activar —, y (2) todo
#: código SIN mapeo se concedía con la sola vista: ``cajero`` y ``solo_lectura``
#: podían habilitar productos por sucursal (lo que vende el POS), gestionar
#: especies, cortes y códigos de barras, crear productos internos, aprobar
#: importaciones externas y cambiar la configuración y las alertas de WhatsApp.
#:
#: Ahora el puente sólo traduce lo que el permiso grueso significa de verdad:
#: ver → consultar, crear → dar de alta, editar → mantener la ficha y sus
#: catálogos, eliminar → bajas. Lo que exige segregación o es sensible
#: (aprobar, activar, bloquear, descontinuar, archivar, reglas de código,
#: clasificación cárnica, surtido por sucursal, productos internos, catálogos
#: externos, configuración, notificaciones, WhatsApp, costo de referencia,
#: bitácora de auditoría)
#: NO tiene equivalente grueso: se concede sólo con su código granular, que la
#: migración 324 siembra por rol. Lo no listado se DENIEGA.
_VER = ("PRODUCTOS.ver",)
_CREAR = ("PRODUCTOS.crear", "CREAR_PRODUCTO")
_EDITAR = ("PRODUCTOS.editar", "EDITAR_PRODUCTO")
_ELIMINAR = ("PRODUCTOS.eliminar", "ELIMINAR_PRODUCTO")

CANONICAL_TO_LEGACY: dict[str, tuple[str, ...]] = {
    # ── consulta ──────────────────────────────────────────────────────────
    ProductPermissions.ACCESS: _VER,
    ProductPermissions.VIEW: _VER,
    ProductPermissions.VIEW_MEAT: _VER,
    ProductPermissions.VIEW_INTERNAL: _VER,
    ProductPermissions.EXPORT: ("PRODUCTOS.exportar", "PRODUCTOS.ver"),
    ProductPermissions.CATEGORIES_VIEW: _VER,
    ProductPermissions.BRANDS_VIEW: _VER,
    ProductPermissions.ATTRIBUTES_VIEW: _VER,
    ProductPermissions.BUNDLES_VIEW: _VER,
    ProductPermissions.SPECIES_VIEW: _VER,
    ProductPermissions.MEAT_CLASSIFICATION_VIEW: _VER,
    ProductPermissions.CUTS_VIEW: _VER,
    ProductPermissions.UNITS_VIEW: _VER,
    ProductPermissions.RECIPE_VIEW: _VER,
    ProductPermissions.YIELD_VIEW: _VER,
    ProductPermissions.CUTTING_SCHEME_VIEW: _VER,
    ProductPermissions.BRANCH_ASSIGNMENT_VIEW: _VER,
    ProductPermissions.SETTINGS_VIEW: _VER,
    # ── alta y mantenimiento de la ficha ──────────────────────────────────
    ProductPermissions.CREATE: _CREAR,
    ProductPermissions.IMPORT_EXECUTE: _CREAR,
    ProductPermissions.EDIT: _EDITAR,
    ProductPermissions.SUBMIT: _EDITAR,
    ProductPermissions.CATEGORIES_MANAGE: _EDITAR,
    ProductPermissions.BRANDS_MANAGE: _EDITAR,
    ProductPermissions.ATTRIBUTES_MANAGE: _EDITAR,
    ProductPermissions.VARIANTS_GENERATE: _EDITAR,
    ProductPermissions.IMAGES_MANAGE: _EDITAR,
    # Unidades y conversiones mueven inventario y costo: nunca con la vista.
    ProductPermissions.UNITS_MANAGE: _EDITAR,
    ProductPermissions.CONVERSIONS_MANAGE: _EDITAR,
    ProductPermissions.BARCODES_MANAGE: _EDITAR,
    ProductPermissions.ALTERNATE_CODES_MANAGE: _EDITAR,
    # Capturar borradores de receta/rendimiento/despiece/combo: sí con edición;
    # aprobarlos y activarlos, no (abajo, sin equivalente grueso).
    ProductPermissions.RECIPE_CREATE: _EDITAR,
    ProductPermissions.RECIPE_EDIT: _EDITAR,
    ProductPermissions.YIELD_CREATE: _EDITAR,
    ProductPermissions.YIELD_EDIT: _EDITAR,
    ProductPermissions.CUTTING_SCHEME_MANAGE: _EDITAR,
    ProductPermissions.BUNDLES_MANAGE: _EDITAR,
    # ── bajas ─────────────────────────────────────────────────────────────
    ProductPermissions.DEACTIVATE: _ELIMINAR,
}

#: Sin mapeo → se deniega (antes se concedía con la vista).
_DEFAULT_LEGACY: tuple[str, ...] = ()


def legacy_codes_for(canonical_code: str) -> tuple[str, ...]:
    return CANONICAL_TO_LEGACY.get(canonical_code, _DEFAULT_LEGACY)


def make_permission_checker(session) -> Callable[[str], bool]:
    """Devuelve ``has(codigo_canonico) -> bool`` sobre la sesión viva.

    Concede si la sesión tiene el código canónico inglés directamente, o cualquiera
    de los códigos legacy mapeados (``session.tiene_permiso``). Sin sesión → deniega.
    """
    if session is None:
        return lambda _code: False
    check = getattr(session, "tiene_permiso", None)
    if not callable(check):
        return lambda _code: False

    def has(canonical_code: str) -> bool:
        if check(canonical_code):  # rol ya migrado al código inglés
            return True
        return any(check(code) for code in legacy_codes_for(canonical_code))

    return has


class SessionPermissionChecker:
    """Adaptador `PermissionChecker` (para `ProductsAuthorizationPolicy`) sobre la
    sesión viva. Concede si el rol tiene el permiso canónico inglés o cualquiera de
    los códigos legacy mapeados (P0-02: el backend re-valida siempre)."""

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        check = getattr(self._session, "tiene_permiso", None)
        if not callable(check):
            return False
        if check(permission_code):
            return True
        return any(check(code) for code in legacy_codes_for(permission_code))
