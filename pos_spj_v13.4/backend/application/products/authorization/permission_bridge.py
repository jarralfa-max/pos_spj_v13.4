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

#: Permiso canónico → códigos legacy que lo conceden (cualquiera basta).
CANONICAL_TO_LEGACY: dict[str, tuple[str, ...]] = {
    ProductPermissions.ACCESS: ("PRODUCTOS.ver",),
    ProductPermissions.VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.VIEW_MEAT: ("PRODUCTOS.ver",),
    ProductPermissions.VIEW_INTERNAL: ("PRODUCTOS.ver",),
    ProductPermissions.VIEW_AUDIT: ("PRODUCTOS.ver",),
    ProductPermissions.EXPORT: ("PRODUCTOS.ver",),
    ProductPermissions.CREATE: ("PRODUCTOS.crear", "CREAR_PRODUCTO"),
    ProductPermissions.EDIT: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.DEACTIVATE: ("PRODUCTOS.eliminar", "ELIMINAR_PRODUCTO"),
    ProductPermissions.ARCHIVE: ("PRODUCTOS.eliminar", "ELIMINAR_PRODUCTO"),
    ProductPermissions.DISCONTINUE: ("PRODUCTOS.eliminar",),
    ProductPermissions.SUBMIT: ("PRODUCTOS.editar",),
    ProductPermissions.APPROVE: ("PRODUCTOS.editar",),
    ProductPermissions.ACTIVATE: ("PRODUCTOS.editar",),
    ProductPermissions.BLOCK: ("PRODUCTOS.editar",),
    # P0-04: sobrescribir el código y gestionar sus reglas son privilegios de
    # edición/configuración — nunca se conceden con la sola vista.
    ProductPermissions.OVERRIDE_CODE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.CODE_RULES_MANAGE: ("PRODUCTOS.configurar",),
    # P1-01: ver categorías con la vista; gestionarlas exige edición.
    ProductPermissions.CATEGORIES_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.CATEGORIES_MANAGE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # P1-02: ver marcas con la vista; gestionarlas exige edición.
    ProductPermissions.BRANDS_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.BRANDS_MANAGE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # P1-03: ver atributos con la vista; gestionarlos/generar variantes exige edición.
    ProductPermissions.ATTRIBUTES_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.ATTRIBUTES_MANAGE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.VARIANTS_GENERATE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # P1: gestionar imágenes es un privilegio de edición del maestro.
    ProductPermissions.IMAGES_MANAGE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # Recetas: ver con la vista; crear/editar/aprobar/activar con edición (nunca
    # se conceden con la sola vista — la segregación exige además dos usuarios).
    ProductPermissions.RECIPE_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.RECIPE_CREATE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.RECIPE_EDIT: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.RECIPE_APPROVE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.RECIPE_ACTIVATE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # Rendimientos (yields): ver con la vista; el resto con edición.
    ProductPermissions.YIELD_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.YIELD_CREATE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.YIELD_EDIT: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.YIELD_APPROVE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    ProductPermissions.YIELD_ACTIVATE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
    # Esquemas de despiece (cutting): ver con la vista; gestionar con edición.
    ProductPermissions.CUTTING_SCHEME_VIEW: ("PRODUCTOS.ver",),
    ProductPermissions.CUTTING_SCHEME_MANAGE: ("PRODUCTOS.editar", "EDITAR_PRODUCTO"),
}

#: Cuando un permiso canónico no está mapeado arriba, se concede con la vista.
_DEFAULT_LEGACY = ("PRODUCTOS.ver",)


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
