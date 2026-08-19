"""Granular products permission codes (§38).

Products is never gated by a single ``PRODUCTOS`` permission. Every sensitive
action — create, submit, approve, activate, block, classify meat, manage cuts,
manage units/conversions/barcodes, create/approve recipes and yields, manage
internal products, assign to branches, import external catalogs — has its own
code, and the backend re-validates it on every use case (hiding a button is not
security). Segregation of duties (§39) sits on top of these codes.

Codes use the app-wide canonical ``MODULO.accion`` format (see
`core/security/permission_catalog.py`), the same convention Compras/Inventario/
Caja/CRM already use — not a parallel flat/unregistered vocabulary. Every value
below is registered 1:1 in `CANONICAL_MODULE_PERMISSIONS["PRODUCTOS"]`, which is
what the Configuración permission matrix, role seeding and
`SessionContext.tiene_permiso()` actually read; a code that only lived here and
not in that catalog could never really be granted to any role. The four
coarse legacy actions (``ver``/``crear``/``editar``/``eliminar``) are reused
verbatim by the corresponding coarse-grained codes below (VIEW/CREATE/EDIT/
DEACTIVATE) so already-seeded roles (admin/gerente/almacen/cajero) keep their
current access without re-seeding; every finer-grained action introduced here
is a brand-new dotted code, not auto-granted to any seeded role (fail-closed —
an admin must grant it explicitly), matching this repo's established
Compras/Inventario permission convention.
"""

from __future__ import annotations

_MOD = "PRODUCTOS"


class ProductPermissions:
    # ── consulta (§38) ────────────────────────────────────────────────────
    ACCESS = f"{_MOD}.acceso"
    VIEW = f"{_MOD}.ver"
    VIEW_COST_REFERENCE = f"{_MOD}.ver.costo_referencia"
    VIEW_INTERNAL = f"{_MOD}.ver.interno"
    VIEW_MEAT = f"{_MOD}.ver.carnico"
    VIEW_AUDIT = f"{_MOD}.ver.auditoria"
    EXPORT = f"{_MOD}.exportar"

    # ── maestro (§38) ─────────────────────────────────────────────────────
    CREATE = f"{_MOD}.crear"
    EDIT = f"{_MOD}.editar"
    SUBMIT = f"{_MOD}.enviar_revision"
    APPROVE = f"{_MOD}.aprobar"
    ACTIVATE = f"{_MOD}.activar"
    BLOCK = f"{_MOD}.bloquear"
    DEACTIVATE = f"{_MOD}.eliminar"
    DISCONTINUE = f"{_MOD}.descontinuar"
    ARCHIVE = f"{_MOD}.archivar"
    OVERRIDE_CODE = f"{_MOD}.codigo.sobrescribir"   # editar manualmente el código (P0-04)
    CODE_RULES_MANAGE = f"{_MOD}.codigo.configurar_reglas"

    # ── categorías jerárquicas (P1-01) ────────────────────────────────────
    CATEGORIES_VIEW = f"{_MOD}.categoria.ver"
    CATEGORIES_MANAGE = f"{_MOD}.categoria.gestionar"

    # ── marcas (P1-02) ─────────────────────────────────────────────────────
    BRANDS_VIEW = f"{_MOD}.marca.ver"
    BRANDS_MANAGE = f"{_MOD}.marca.gestionar"

    # ── atributos / variantes (P1-03) ──────────────────────────────────────
    ATTRIBUTES_VIEW = f"{_MOD}.atributo.ver"
    ATTRIBUTES_MANAGE = f"{_MOD}.atributo.gestionar"
    VARIANTS_GENERATE = f"{_MOD}.variante.generar"

    # ── imágenes (P1) ──────────────────────────────────────────────────────
    IMAGES_MANAGE = f"{_MOD}.imagen.gestionar"

    # ── combos / kits (§28) ────────────────────────────────────────────────
    BUNDLES_VIEW = f"{_MOD}.combo.ver"
    BUNDLES_MANAGE = f"{_MOD}.combo.gestionar"

    # ── clasificación cárnica (§38) ───────────────────────────────────────
    SPECIES_VIEW = f"{_MOD}.especie.ver"
    SPECIES_MANAGE = f"{_MOD}.especie.gestionar"
    MEAT_CLASSIFICATION_VIEW = f"{_MOD}.clasificacion_carnica.ver"
    MEAT_CLASSIFICATION_MANAGE = f"{_MOD}.clasificacion_carnica.gestionar"
    CUTS_VIEW = f"{_MOD}.corte.ver"
    CUTS_MANAGE = f"{_MOD}.corte.gestionar"

    # ── unidades y códigos (§38) ──────────────────────────────────────────
    UNITS_VIEW = f"{_MOD}.unidad.ver"
    UNITS_MANAGE = f"{_MOD}.unidad.gestionar"
    CONVERSIONS_MANAGE = f"{_MOD}.conversion.gestionar"
    BARCODES_MANAGE = f"{_MOD}.codigo_barras.gestionar"
    ALTERNATE_CODES_MANAGE = f"{_MOD}.codigo_alterno.gestionar"

    # ── recetas y rendimiento (§38) ───────────────────────────────────────
    RECIPE_VIEW = f"{_MOD}.receta.ver"
    RECIPE_CREATE = f"{_MOD}.receta.crear"
    RECIPE_EDIT = f"{_MOD}.receta.editar"
    RECIPE_APPROVE = f"{_MOD}.receta.aprobar"
    RECIPE_ACTIVATE = f"{_MOD}.receta.activar"

    YIELD_VIEW = f"{_MOD}.rendimiento.ver"
    YIELD_CREATE = f"{_MOD}.rendimiento.crear"
    YIELD_EDIT = f"{_MOD}.rendimiento.editar"
    YIELD_APPROVE = f"{_MOD}.rendimiento.aprobar"
    YIELD_ACTIVATE = f"{_MOD}.rendimiento.activar"

    CUTTING_SCHEME_VIEW = f"{_MOD}.despiece.ver"
    CUTTING_SCHEME_MANAGE = f"{_MOD}.despiece.gestionar"

    # ── productos internos (§38) ──────────────────────────────────────────
    INTERNAL_VIEW = f"{_MOD}.interno.ver"
    INTERNAL_CREATE = f"{_MOD}.interno.crear"
    INTERNAL_EDIT = f"{_MOD}.interno.editar"
    INTERNAL_ACTIVATE = f"{_MOD}.interno.activar"

    # ── surtido y sucursales (§38) ────────────────────────────────────────
    BRANCH_ASSIGNMENT_VIEW = f"{_MOD}.sucursal.ver"
    BRANCH_ASSIGNMENT_MANAGE = f"{_MOD}.sucursal.gestionar"
    ASSORTMENT_MANAGE = f"{_MOD}.surtido.gestionar"

    # ── integraciones (§38) ───────────────────────────────────────────────
    EXTERNAL_SEARCH = f"{_MOD}.externo.buscar"
    EXTERNAL_IMPORT = f"{_MOD}.externo.importar"
    EXTERNAL_REVIEW = f"{_MOD}.externo.revisar"
    EXTERNAL_APPROVE = f"{_MOD}.externo.aprobar"
    IMPORT_EXECUTE = f"{_MOD}.importacion.ejecutar"
    IMPORT_APPROVE = f"{_MOD}.importacion.aprobar"

    # ── configuración (§38) ───────────────────────────────────────────────
    SETTINGS_VIEW = f"{_MOD}.configuracion.ver"
    SETTINGS_MANAGE = f"{_MOD}.configuracion.editar"
    NOTIFICATIONS_MANAGE = f"{_MOD}.notificacion.gestionar"
    WHATSAPP_ALERTS_MANAGE = f"{_MOD}.whatsapp.gestionar"


ALL_PRODUCT_PERMISSIONS = frozenset(
    v for k, v in vars(ProductPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)


# Permisos que exigen ver productos sensibles: la UI/POS no expone internos ni
# datos de costo sin el permiso específico (§33, §37-38).
COST_REFERENCE_PERMISSION = ProductPermissions.VIEW_COST_REFERENCE
INTERNAL_VIEW_PERMISSION = ProductPermissions.VIEW_INTERNAL
MEAT_VIEW_PERMISSION = ProductPermissions.VIEW_MEAT


# Pares crea → aprueba/activa que la segregación de funciones vigila (§39).
SEGREGATED_APPROVALS = {
    ProductPermissions.RECIPE_APPROVE: ProductPermissions.RECIPE_CREATE,
    ProductPermissions.RECIPE_ACTIVATE: ProductPermissions.RECIPE_CREATE,
    ProductPermissions.YIELD_APPROVE: ProductPermissions.YIELD_CREATE,
    ProductPermissions.YIELD_ACTIVATE: ProductPermissions.YIELD_CREATE,
    ProductPermissions.APPROVE: ProductPermissions.CREATE,
    ProductPermissions.EXTERNAL_APPROVE: ProductPermissions.EXTERNAL_IMPORT,
    ProductPermissions.IMPORT_APPROVE: ProductPermissions.IMPORT_EXECUTE,
}
