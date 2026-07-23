"""Products bounded context — born-clean UUIDv7 schema (single source of truth).

Rules (REGLA CERO / §8 / §48):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- No ``existencia``/``stock`` column and no final price column live here: stock
  belongs to Inventory, price to Pricing (guardrails
  ``test_product_master_does_not_store_stock`` / ``..._does_not_own_pricing``).
  Any decimal that *does* belong to Products later (weights, conversions, yields)
  is ``TEXT`` decimal (PostgreSQL: NUMERIC), never REAL.
- Control flags are ``INTEGER`` 0/1 with CHECK, not free text.
- Classification (category/species/unit) is stored as an id (FK), never as text.
- Structural idempotency: UNIQUE(code) on products, UNIQUE(species,code) on
  regions/cuts, UNIQUE(operation_id)/UNIQUE(event_id) on audit/outbox.

Canonical English names (``products``, ``species``, ``anatomical_regions``,
``cut_classifications``) do NOT collide with the legacy Spanish tables
(``productos``, ``recetas``, ``rendimiento_pollo`` …), which keep their live
readers until PROD-17 migrates them and PROD-19 drops them (see
``products_schema_consolidation.md``).

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

PRODUCT_TABLES: tuple[str, ...] = (
    "species",
    "anatomical_regions",
    "cut_classifications",
    "units_of_measure",
    "product_unit_conversions",
    "product_catch_weight_config",
    "product_barcodes",
    "product_alternate_codes",
    "product_shelf_life_profiles",
    "product_quality_profiles",
    "product_logistics_profiles",
    "recipes",
    "recipe_versions",
    "recipe_components",
    "recipe_outputs",
    "yield_profiles",
    "yield_profile_versions",
    "yield_outputs",
    "cutting_schemes",
    "cutting_scheme_versions",
    "cutting_outputs",
    "product_bundles",
    "bundle_versions",
    "bundle_components",
    "products",
    "product_authorization_log",
    "product_audit_log",
    "product_outbox",
    "product_processed_events",
)

_DDL = (
    # ── clasificación cárnica (PROD-3) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS species (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS anatomical_regions (
        id TEXT PRIMARY KEY,
        species_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(species_id, code),
        FOREIGN KEY (species_id) REFERENCES species(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cut_classifications (
        id TEXT PRIMARY KEY,
        species_id TEXT NOT NULL,
        anatomical_region_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        cut_level TEXT NOT NULL,            -- CARCASS | PRIMARY | SECONDARY | PORTION
        bone_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
        fat_class TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
        quality_grade TEXT,
        parent_cut_id TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(species_id, code),
        FOREIGN KEY (species_id) REFERENCES species(id),
        FOREIGN KEY (anatomical_region_id) REFERENCES anatomical_regions(id),
        FOREIGN KEY (parent_cut_id) REFERENCES cut_classifications(id)
    )
    """,
    # ── unidades / conversiones / peso variable (PROD-5) ──────────────────
    """
    CREATE TABLE IF NOT EXISTS units_of_measure (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        dimension TEXT NOT NULL,            -- WEIGHT | COUNT | VOLUME | ...
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_unit_conversions (
        id TEXT PRIMARY KEY,
        product_id TEXT,                    -- NULL = conversión global
        from_unit_id TEXT NOT NULL,
        to_unit_id TEXT NOT NULL,
        factor TEXT NOT NULL,               -- Decimal string (no REAL)
        rounding_scale INTEGER NOT NULL DEFAULT 6,
        effective_from TEXT,
        effective_to TEXT,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (from_unit_id) REFERENCES units_of_measure(id),
        FOREIGN KEY (to_unit_id) REFERENCES units_of_measure(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_catch_weight_config (
        product_id TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        nominal_unit_id TEXT,
        weight_unit_id TEXT,
        minimum_weight TEXT,                -- Decimal string
        maximum_weight TEXT,
        average_weight TEXT,
        tolerance_pct TEXT NOT NULL DEFAULT '0',
        price_basis TEXT NOT NULL DEFAULT 'PER_KILOGRAM',
        label_required INTEGER NOT NULL DEFAULT 1 CHECK(label_required IN (0,1)),
        scale_barcode_enabled INTEGER NOT NULL DEFAULT 0 CHECK(scale_barcode_enabled IN (0,1)),
        updated_at TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (nominal_unit_id) REFERENCES units_of_measure(id),
        FOREIGN KEY (weight_unit_id) REFERENCES units_of_measure(id)
    )
    """,
    # ── códigos / barcodes (PROD-7) ───────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS product_barcodes (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        variant_id TEXT,
        barcode_value TEXT NOT NULL,
        barcode_type TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0,1)),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # Unicidad de códigos ACTIVOS (§17): un valor activo pertenece a un producto.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_barcode_active_value
        ON product_barcodes(barcode_value) WHERE active = 1
    """,
    """
    CREATE TABLE IF NOT EXISTS product_alternate_codes (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        code TEXT NOT NULL,
        code_type TEXT NOT NULL DEFAULT 'SUPPLIER_CODE',
        supplier_id TEXT,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # ── calidad / vida útil / logística (PROD-8) ──────────────────────────
    """
    CREATE TABLE IF NOT EXISTS product_shelf_life_profiles (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        shelf_life_days INTEGER NOT NULL,
        minimum_remaining_for_receipt INTEGER NOT NULL DEFAULT 0,
        minimum_remaining_for_sale INTEGER NOT NULL DEFAULT 0,
        storage_condition TEXT NOT NULL DEFAULT 'AMBIENT',
        opened_shelf_life_days INTEGER NOT NULL DEFAULT 0,
        frozen_shelf_life_days INTEGER NOT NULL DEFAULT 0,
        thawed_shelf_life_days INTEGER NOT NULL DEFAULT 0,
        effective_from TEXT,
        effective_to TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_quality_profiles (
        product_id TEXT PRIMARY KEY,
        inspection_required INTEGER NOT NULL DEFAULT 0,
        temperature_required INTEGER NOT NULL DEFAULT 0,
        weight_check_required INTEGER NOT NULL DEFAULT 0,
        organoleptic_check_required INTEGER NOT NULL DEFAULT 0,
        microbiological_test_required INTEGER NOT NULL DEFAULT 0,
        fat_pct_min TEXT, fat_pct_max TEXT,
        moisture_pct_min TEXT, moisture_pct_max TEXT,
        color_requirement TEXT, odor_requirement TEXT,
        packaging_requirement TEXT, documentation_requirement TEXT,
        quarantine_required INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_logistics_profiles (
        product_id TEXT PRIMARY KEY,
        gross_weight TEXT, net_weight TEXT, weight_unit TEXT NOT NULL DEFAULT 'KG',
        dimensions TEXT,
        storage_temp_min TEXT, storage_temp_max TEXT, storage_temp_unit TEXT,
        transport_temp_min TEXT, transport_temp_max TEXT, transport_temp_unit TEXT,
        fragile INTEGER NOT NULL DEFAULT 0,
        perishable INTEGER NOT NULL DEFAULT 0,
        frozen INTEGER NOT NULL DEFAULT 0,
        chilled INTEGER NOT NULL DEFAULT 0,
        stackable INTEGER NOT NULL DEFAULT 1,
        shelf_life_days INTEGER NOT NULL DEFAULT 0,
        open_package_shelf_life_days INTEGER NOT NULL DEFAULT 0,
        requires_cold_chain INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # ── recetas / BOM (PROD-9) ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS recipes (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        recipe_type TEXT NOT NULL,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_versions (
        id TEXT PRIMARY KEY,
        recipe_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        effective_from TEXT,
        effective_to TEXT,
        approved_by_user_id TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(recipe_id, version_number),
        FOREIGN KEY (recipe_id) REFERENCES recipes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_components (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        component_product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,             -- Decimal string
        unit_id TEXT NOT NULL,
        scrap_pct TEXT NOT NULL DEFAULT '0',
        sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (version_id) REFERENCES recipe_versions(id),
        FOREIGN KEY (component_product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_outputs (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        output_type TEXT NOT NULL,
        quantity TEXT NOT NULL,             -- Decimal string
        unit_id TEXT NOT NULL,
        expected_yield_pct TEXT,
        sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (version_id) REFERENCES recipe_versions(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # ── rendimientos (PROD-10) ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS yield_profiles (
        id TEXT PRIMARY KEY,
        input_product_id TEXT NOT NULL,
        species_id TEXT,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (input_product_id) REFERENCES products(id),
        FOREIGN KEY (species_id) REFERENCES species(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS yield_profile_versions (
        id TEXT PRIMARY KEY,
        yield_profile_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        tolerance_pct TEXT NOT NULL DEFAULT '0',
        effective_from TEXT,
        effective_to TEXT,
        approved_by_user_id TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(yield_profile_id, version_number),
        FOREIGN KEY (yield_profile_id) REFERENCES yield_profiles(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS yield_outputs (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        output_type TEXT NOT NULL,
        expected_yield_pct TEXT NOT NULL,
        expected_quantity TEXT NOT NULL DEFAULT '0',
        minimum_yield_pct TEXT,
        maximum_yield_pct TEXT,
        unit_id TEXT NOT NULL,
        cost_allocation_weight TEXT NOT NULL DEFAULT '0',
        sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (version_id) REFERENCES yield_profile_versions(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # ── esquemas de despiece (PROD-11) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cutting_schemes (
        id TEXT PRIMARY KEY,
        input_product_id TEXT NOT NULL,
        species_id TEXT NOT NULL,
        name TEXT NOT NULL,
        cut_level TEXT NOT NULL DEFAULT 'PRIMARY',
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (input_product_id) REFERENCES products(id),
        FOREIGN KEY (species_id) REFERENCES species(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cutting_scheme_versions (
        id TEXT PRIMARY KEY,
        cutting_scheme_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        effective_from TEXT,
        effective_to TEXT,
        approved_by_user_id TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(cutting_scheme_id, version_number),
        FOREIGN KEY (cutting_scheme_id) REFERENCES cutting_schemes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cutting_outputs (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        output_type TEXT NOT NULL DEFAULT 'MAIN_PRODUCT',
        measure_kind TEXT NOT NULL,         -- BY_PIECE | BY_WEIGHT
        quantity TEXT NOT NULL,             -- Decimal string
        unit_id TEXT NOT NULL,
        cut_classification_id TEXT,
        cut_level TEXT,
        bone_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
        sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (version_id) REFERENCES cutting_scheme_versions(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    # ── combos / kits / paquetes (PROD-13) ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS product_bundles (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        bundle_type TEXT NOT NULL,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bundle_versions (
        id TEXT PRIMARY KEY,
        bundle_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        effective_from TEXT,
        effective_to TEXT,
        approved_by_user_id TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(bundle_id, version_number),
        FOREIGN KEY (bundle_id) REFERENCES product_bundles(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bundle_components (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        component_product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,             -- Decimal string
        unit_id TEXT NOT NULL,
        optional INTEGER NOT NULL DEFAULT 0 CHECK(optional IN (0,1)),
        substitutable INTEGER NOT NULL DEFAULT 0 CHECK(substitutable IN (0,1)),
        sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (version_id) REFERENCES bundle_versions(id),
        FOREIGN KEY (component_product_id) REFERENCES products(id)
    )
    """,
    # ── product master (PROD-2) ───────────────────────────────────────────
    #   NOTE: no existencia, no precio. Stock → Inventory, price → Pricing.
    """
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        name_normalized TEXT NOT NULL DEFAULT '',
        short_name TEXT,
        description TEXT,
        product_type TEXT NOT NULL,
        lifecycle_status TEXT NOT NULL DEFAULT 'DRAFT',
        internal_stage TEXT NOT NULL DEFAULT 'NONE',
        category_id TEXT,
        brand_id TEXT,
        species_id TEXT,
        base_unit_id TEXT NOT NULL,
        tax_profile_id TEXT,
        country_of_origin TEXT,
        sellable INTEGER NOT NULL DEFAULT 0 CHECK(sellable IN (0,1)),
        purchasable INTEGER NOT NULL DEFAULT 0 CHECK(purchasable IN (0,1)),
        inventory_managed INTEGER NOT NULL DEFAULT 0 CHECK(inventory_managed IN (0,1)),
        producible INTEGER NOT NULL DEFAULT 0 CHECK(producible IN (0,1)),
        internal_only INTEGER NOT NULL DEFAULT 0 CHECK(internal_only IN (0,1)),
        recipe_allowed INTEGER NOT NULL DEFAULT 0 CHECK(recipe_allowed IN (0,1)),
        bundle_allowed INTEGER NOT NULL DEFAULT 0 CHECK(bundle_allowed IN (0,1)),
        lot_controlled INTEGER NOT NULL DEFAULT 0 CHECK(lot_controlled IN (0,1)),
        serial_controlled INTEGER NOT NULL DEFAULT 0 CHECK(serial_controlled IN (0,1)),
        expiration_controlled INTEGER NOT NULL DEFAULT 0 CHECK(expiration_controlled IN (0,1)),
        catch_weight_enabled INTEGER NOT NULL DEFAULT 0 CHECK(catch_weight_enabled IN (0,1)),
        quality_controlled INTEGER NOT NULL DEFAULT 0 CHECK(quality_controlled IN (0,1)),
        traceability_required INTEGER NOT NULL DEFAULT 0 CHECK(traceability_required IN (0,1)),
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT,
        activated_at TEXT,
        discontinued_at TEXT,
        FOREIGN KEY (species_id) REFERENCES species(id)
    )
    """,
    # ── seguridad / auditoría (PROD-1) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS product_authorization_log (
        id TEXT PRIMARY KEY,
        permission_code TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        authorized_by TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        entity_id TEXT,
        device_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_audit_log (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        authorized_by TEXT,
        operation_id TEXT NOT NULL,
        before TEXT,
        after TEXT,
        reason TEXT,
        branch_id TEXT,
        source TEXT NOT NULL DEFAULT 'products',
        occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # ── outbox / idempotencia de eventos (§46) ────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS product_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        operation_id TEXT,
        entity_id TEXT,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        processed_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_products_type ON products(product_type)",
    "CREATE INDEX IF NOT EXISTS idx_products_status ON products(lifecycle_status)",
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_species ON products(species_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_name_norm ON products(name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_regions_species ON anatomical_regions(species_id)",
    "CREATE INDEX IF NOT EXISTS idx_cuts_species ON cut_classifications(species_id)",
    "CREATE INDEX IF NOT EXISTS idx_cuts_region ON cut_classifications(anatomical_region_id)",
    "CREATE INDEX IF NOT EXISTS idx_cuts_parent ON cut_classifications(parent_cut_id)",
    "CREATE INDEX IF NOT EXISTS idx_units_dimension ON units_of_measure(dimension)",
    "CREATE INDEX IF NOT EXISTS idx_conv_product ON product_unit_conversions(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_conv_from_to ON product_unit_conversions(from_unit_id, to_unit_id)",
    "CREATE INDEX IF NOT EXISTS idx_barcodes_product ON product_barcodes(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_barcodes_type ON product_barcodes(barcode_type)",
    "CREATE INDEX IF NOT EXISTS idx_altcodes_product ON product_alternate_codes(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_altcodes_code ON product_alternate_codes(code)",
    "CREATE INDEX IF NOT EXISTS idx_shelf_life_product ON product_shelf_life_profiles(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_recipes_product ON recipes(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_recipe_versions_recipe ON recipe_versions(recipe_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_recipe_components_version ON recipe_components(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_recipe_outputs_version ON recipe_outputs(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_yield_profiles_input ON yield_profiles(input_product_id)",
    "CREATE INDEX IF NOT EXISTS idx_yield_versions_profile ON yield_profile_versions(yield_profile_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_yield_outputs_version ON yield_outputs(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_cutting_schemes_input ON cutting_schemes(input_product_id)",
    "CREATE INDEX IF NOT EXISTS idx_cutting_schemes_species ON cutting_schemes(species_id)",
    "CREATE INDEX IF NOT EXISTS idx_cutting_versions_scheme ON cutting_scheme_versions(cutting_scheme_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_cutting_outputs_version ON cutting_outputs(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_bundles_product ON product_bundles(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_bundle_versions_bundle ON bundle_versions(bundle_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_bundle_components_version ON bundle_components(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_prod_audit_entity ON product_audit_log(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_prod_audit_op ON product_audit_log(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_prod_authz_op ON product_authorization_log(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_prod_outbox_status ON product_outbox(status)",
)


def create_products_schema(conn) -> None:
    """Create the canonical products schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_products_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(PRODUCT_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
