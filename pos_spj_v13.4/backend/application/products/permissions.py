"""Granular products permission codes (§38).

Products is never gated by a single ``PRODUCTOS`` permission. Every sensitive
action — create, submit, approve, activate, block, classify meat, manage cuts,
manage units/conversions/barcodes, create/approve recipes and yields, manage
internal products, assign to branches, import external catalogs — has its own
code, and the backend re-validates it on every use case (hiding a button is not
security). Segregation of duties (§39) sits on top of these codes.
"""

from __future__ import annotations


class ProductPermissions:
    # ── consulta (§38) ────────────────────────────────────────────────────
    ACCESS = "PRODUCTS_ACCESS"
    VIEW = "PRODUCTS_VIEW"
    VIEW_COST_REFERENCE = "PRODUCTS_VIEW_COST_REFERENCE"
    VIEW_INTERNAL = "PRODUCTS_VIEW_INTERNAL"
    VIEW_MEAT = "PRODUCTS_VIEW_MEAT"
    VIEW_AUDIT = "PRODUCTS_VIEW_AUDIT"
    EXPORT = "PRODUCTS_EXPORT"

    # ── maestro (§38) ─────────────────────────────────────────────────────
    CREATE = "PRODUCTS_CREATE"
    EDIT = "PRODUCTS_EDIT"
    SUBMIT = "PRODUCTS_SUBMIT"
    APPROVE = "PRODUCTS_APPROVE"
    ACTIVATE = "PRODUCTS_ACTIVATE"
    BLOCK = "PRODUCTS_BLOCK"
    DEACTIVATE = "PRODUCTS_DEACTIVATE"
    DISCONTINUE = "PRODUCTS_DISCONTINUE"
    ARCHIVE = "PRODUCTS_ARCHIVE"

    # ── clasificación cárnica (§38) ───────────────────────────────────────
    SPECIES_VIEW = "PRODUCTS_SPECIES_VIEW"
    SPECIES_MANAGE = "PRODUCTS_SPECIES_MANAGE"
    MEAT_CLASSIFICATION_VIEW = "PRODUCTS_MEAT_CLASSIFICATION_VIEW"
    MEAT_CLASSIFICATION_MANAGE = "PRODUCTS_MEAT_CLASSIFICATION_MANAGE"
    CUTS_VIEW = "PRODUCTS_CUTS_VIEW"
    CUTS_MANAGE = "PRODUCTS_CUTS_MANAGE"

    # ── unidades y códigos (§38) ──────────────────────────────────────────
    UNITS_VIEW = "PRODUCTS_UNITS_VIEW"
    UNITS_MANAGE = "PRODUCTS_UNITS_MANAGE"
    CONVERSIONS_MANAGE = "PRODUCTS_CONVERSIONS_MANAGE"
    BARCODES_MANAGE = "PRODUCTS_BARCODES_MANAGE"
    ALTERNATE_CODES_MANAGE = "PRODUCTS_ALTERNATE_CODES_MANAGE"

    # ── recetas y rendimiento (§38) ───────────────────────────────────────
    RECIPE_VIEW = "PRODUCTS_RECIPE_VIEW"
    RECIPE_CREATE = "PRODUCTS_RECIPE_CREATE"
    RECIPE_EDIT = "PRODUCTS_RECIPE_EDIT"
    RECIPE_APPROVE = "PRODUCTS_RECIPE_APPROVE"
    RECIPE_ACTIVATE = "PRODUCTS_RECIPE_ACTIVATE"

    YIELD_VIEW = "PRODUCTS_YIELD_VIEW"
    YIELD_CREATE = "PRODUCTS_YIELD_CREATE"
    YIELD_EDIT = "PRODUCTS_YIELD_EDIT"
    YIELD_APPROVE = "PRODUCTS_YIELD_APPROVE"
    YIELD_ACTIVATE = "PRODUCTS_YIELD_ACTIVATE"

    CUTTING_SCHEME_VIEW = "PRODUCTS_CUTTING_SCHEME_VIEW"
    CUTTING_SCHEME_MANAGE = "PRODUCTS_CUTTING_SCHEME_MANAGE"

    # ── productos internos (§38) ──────────────────────────────────────────
    INTERNAL_VIEW = "PRODUCTS_INTERNAL_VIEW"
    INTERNAL_CREATE = "PRODUCTS_INTERNAL_CREATE"
    INTERNAL_EDIT = "PRODUCTS_INTERNAL_EDIT"
    INTERNAL_ACTIVATE = "PRODUCTS_INTERNAL_ACTIVATE"

    # ── surtido y sucursales (§38) ────────────────────────────────────────
    BRANCH_ASSIGNMENT_VIEW = "PRODUCTS_BRANCH_ASSIGNMENT_VIEW"
    BRANCH_ASSIGNMENT_MANAGE = "PRODUCTS_BRANCH_ASSIGNMENT_MANAGE"
    ASSORTMENT_MANAGE = "PRODUCTS_ASSORTMENT_MANAGE"

    # ── integraciones (§38) ───────────────────────────────────────────────
    EXTERNAL_SEARCH = "PRODUCTS_EXTERNAL_SEARCH"
    EXTERNAL_IMPORT = "PRODUCTS_EXTERNAL_IMPORT"
    EXTERNAL_REVIEW = "PRODUCTS_EXTERNAL_REVIEW"
    EXTERNAL_APPROVE = "PRODUCTS_EXTERNAL_APPROVE"
    IMPORT_EXECUTE = "PRODUCTS_IMPORT_EXECUTE"
    IMPORT_APPROVE = "PRODUCTS_IMPORT_APPROVE"

    # ── configuración (§38) ───────────────────────────────────────────────
    SETTINGS_VIEW = "PRODUCTS_SETTINGS_VIEW"
    SETTINGS_MANAGE = "PRODUCTS_SETTINGS_MANAGE"
    NOTIFICATIONS_MANAGE = "PRODUCTS_NOTIFICATIONS_MANAGE"
    WHATSAPP_ALERTS_MANAGE = "PRODUCTS_WHATSAPP_ALERTS_MANAGE"


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
