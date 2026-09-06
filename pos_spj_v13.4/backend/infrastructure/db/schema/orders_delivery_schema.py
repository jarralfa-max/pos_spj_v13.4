"""Pedidos/Delivery bounded context — born-clean UUIDv7 schema (ORD-3).
Mirrors backend/infrastructure/db/schema/loyalty_schema.py's conventions
exactly.

Rules (REGLA CERO / §8 / §32-42):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Every money/quantity/weight column is a ``TEXT`` decimal string (PostgreSQL:
  NUMERIC); no REAL — floats are forbidden. Conversion to/from ``Decimal``
  happens in the repository layer (a future phase, not built yet), never in
  SQL.
- Structural idempotency (§58): ``UNIQUE(operation_id)`` on
  ``customer_orders`` and ``orders_delivery_outbox``.
- Status/enum values are NOT enforced via SQL CHECK — the domain layer
  (``backend/domain/orders_delivery/enums.py`` + entities/policies) is the
  single source of truth for valid transitions, matching this repo's
  established convention (sales_schema.py/loyalty_schema.py have zero enum
  CHECK constraints either).

Canonical English names (``customer_orders``, ``customer_order_lines``,
``orders_delivery_outbox``) do NOT collide with the legacy operational tables
this bounded context does not touch or replace yet (``delivery_orders``,
``delivery_items``, ``delivery_order_history``, ``pedidos_whatsapp``,
``pedidos_whatsapp_items`` — see
``docs/refactor/orders_delivery_legacy_inventory.md`` §1/§3). These are NEW
tables for the ``CustomerOrder``/``CustomerOrderLine`` aggregate built in
ORD-2 — they back a parallel, not-yet-wired domain, same relationship
LOY-2/LOY-3's new loyalty tables have with the legacy Growth Engine tables.

``customer_orders.customer_id`` references the NEW Customer Master
``customers`` table (UUIDv7) logically, not the legacy ``clientes`` table —
same precedent ``loyalty_accounts.customer_id`` already established
(backend/infrastructure/db/schema/loyalty_schema.py). The legacy
``clientes.id``-vs-``customers.id`` identity bridge
(``docs/refactor/orders_delivery_legacy_inventory.md`` §4.1) stays an open
item for the EXISTING ``core/delivery/`` code, resolved separately; new code
must never target the legacy identity space.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

ORDERS_DELIVERY_TABLES: tuple[str, ...] = (
    "customer_orders",
    "customer_order_lines",
    "order_addresses",
    "delivery_zones",
    "order_packages",
    "delivery_jobs",
    "delivery_attempts",
    "driver_operational_profiles",
    "delivery_assignments",
    "delivery_routes",
    "delivery_route_stops",
    "redelivery_requests",
    "driver_cash_collections",
    "driver_settlements",
    "orders_delivery_outbox",
)

_DDL = (
    # ── CustomerOrder (backend/domain/orders_delivery/entities.py) ─────────
    """
    CREATE TABLE IF NOT EXISTS customer_orders (
        id TEXT NOT NULL PRIMARY KEY,
        order_number TEXT UNIQUE,
        branch_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        order_type TEXT NOT NULL,
        fulfillment_type TEXT NOT NULL,
        customer_id TEXT,
        contact_name TEXT,
        contact_phone TEXT,
        delivery_address_id TEXT,
        requested_delivery_window TEXT,
        scheduled_for TEXT,
        delivery_window_start TEXT,
        delivery_window_end TEXT,
        activation_at TEXT,
        schedule_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
        preparation_status TEXT NOT NULL DEFAULT 'PENDING',
        assigned_to_user_id TEXT,
        station_id TEXT,
        preparation_started_at TEXT,
        preparation_completed_at TEXT,
        pickup_verification_code TEXT,
        priority TEXT,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        payment_status TEXT NOT NULL DEFAULT 'UNPAID',
        fulfillment_status TEXT NOT NULL DEFAULT 'PENDING',
        customer_approval_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED',
        customer_approval_expires_at TEXT,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        subtotal TEXT NOT NULL DEFAULT '0',
        discount_total TEXT NOT NULL DEFAULT '0',
        delivery_fee TEXT NOT NULL DEFAULT '0',
        tax_total TEXT NOT NULL DEFAULT '0',
        rounding_adjustment TEXT NOT NULL DEFAULT '0',
        grand_total TEXT NOT NULL DEFAULT '0',
        external_order_reference TEXT,
        sale_id TEXT,
        quote_id TEXT,
        whatsapp_order_id TEXT,
        operation_id TEXT NOT NULL UNIQUE,
        created_by_user_id TEXT,
        confirmed_by_user_id TEXT,
        cancelled_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(channel, external_order_reference)
    )
    """,
    # ── CustomerOrderLine (owned entity) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS customer_order_lines (
        id TEXT NOT NULL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES customer_orders(id),
        product_id TEXT NOT NULL,
        variant_id TEXT,
        requested_quantity TEXT,
        requested_quantity_unit TEXT,
        requested_weight TEXT,
        requested_weight_unit TEXT,
        prepared_quantity TEXT,
        prepared_quantity_unit TEXT,
        prepared_weight TEXT,
        prepared_weight_unit TEXT,
        final_quantity TEXT,
        final_quantity_unit TEXT,
        final_weight TEXT,
        final_weight_unit TEXT,
        unit_price_snapshot TEXT NOT NULL DEFAULT '0',
        discount_snapshot TEXT NOT NULL DEFAULT '0',
        tax_snapshot TEXT NOT NULL DEFAULT '0',
        catch_weight_enabled INTEGER NOT NULL DEFAULT 0,
        substitution_allowed INTEGER NOT NULL DEFAULT 1,
        substitution_type TEXT,
        substitute_product_id TEXT,
        substitution_reason TEXT,
        pre_substitution_unit_price TEXT,
        proposed_substitution_unit_price TEXT,
        customer_notes TEXT,
        preparation_notes TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        inventory_reservation_id TEXT,
        package_id TEXT,
        product_snapshot_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── OrderAddress (backend/domain/orders_delivery/address.py, §20) ──────
    """
    CREATE TABLE IF NOT EXISTS order_addresses (
        id TEXT NOT NULL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES customer_orders(id),
        recipient_name TEXT NOT NULL,
        recipient_phone TEXT NOT NULL,
        street TEXT NOT NULL,
        exterior_number TEXT NOT NULL DEFAULT '',
        interior_number TEXT,
        neighborhood TEXT,
        postal_code TEXT,
        municipality TEXT,
        state TEXT,
        "references" TEXT,
        latitude REAL,
        longitude REAL,
        geocoding_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
        delivery_zone_id TEXT REFERENCES delivery_zones(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DeliveryZone (backend/domain/orders_delivery/delivery_zone.py, §21) ─
    """
    CREATE TABLE IF NOT EXISTS delivery_zones (
        id TEXT NOT NULL PRIMARY KEY,
        branch_id TEXT NOT NULL,
        name TEXT NOT NULL,
        postal_codes_json TEXT NOT NULL DEFAULT '[]',
        minimum_order TEXT NOT NULL DEFAULT '0',
        delivery_fee TEXT NOT NULL DEFAULT '0',
        free_delivery_threshold TEXT,
        estimated_minutes INTEGER,
        maximum_distance_km TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── OrderPackage (backend/domain/orders_delivery/package.py, §29) ──────
    """
    CREATE TABLE IF NOT EXISTS order_packages (
        id TEXT NOT NULL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES customer_orders(id),
        package_number TEXT NOT NULL,
        package_type TEXT NOT NULL,
        tare TEXT NOT NULL DEFAULT '0',
        gross_weight TEXT NOT NULL DEFAULT '0',
        temperature TEXT,
        seal_number TEXT,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(order_id, package_number)
    )
    """,
    # ── DeliveryJob (backend/domain/orders_delivery/delivery_job.py, §31) ──
    # Deliberately SEPARATE from customer_orders (master prompt §5) —
    # references order_id, never embedded/joined by design.
    """
    CREATE TABLE IF NOT EXISTS delivery_jobs (
        id TEXT NOT NULL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES customer_orders(id),
        branch_id TEXT NOT NULL,
        delivery_number TEXT UNIQUE,
        delivery_zone_id TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING_ASSIGNMENT',
        priority TEXT,
        assigned_driver_id TEXT,
        route_id TEXT,
        scheduled_window_start TEXT,
        scheduled_window_end TEXT,
        estimated_arrival_at TEXT,
        dispatched_at TEXT,
        delivered_at TEXT,
        failed_at TEXT,
        delivery_fee TEXT NOT NULL DEFAULT '0',
        cash_to_collect TEXT NOT NULL DEFAULT '0',
        payment_method_expected TEXT,
        operation_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DeliveryAttempt (backend/domain/orders_delivery/delivery_job.py, §38-40) ─
    """
    CREATE TABLE IF NOT EXISTS delivery_attempts (
        id TEXT NOT NULL PRIMARY KEY,
        delivery_job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
        successful INTEGER NOT NULL,
        recipient_name TEXT,
        signature_reference TEXT,
        photo_reference TEXT,
        pin_verified INTEGER NOT NULL DEFAULT 0,
        latitude REAL,
        longitude REAL,
        evidence_notes TEXT,
        failure_reason TEXT,
        attempted_at TEXT NOT NULL
    )
    """,
    # ── DriverOperationalProfile (backend/domain/orders_delivery/driver.py, §34) ─
    # Identity lives in RRHH/Usuarios — this table only tracks operational
    # facts (§33: never a parallel people table).
    """
    CREATE TABLE IF NOT EXISTS driver_operational_profiles (
        id TEXT NOT NULL PRIMARY KEY,
        driver_id TEXT NOT NULL UNIQUE,
        branch_id TEXT NOT NULL,
        vehicle_type TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        capacity INTEGER NOT NULL DEFAULT 1,
        current_assignment_count INTEGER NOT NULL DEFAULT 0,
        cash_limit TEXT NOT NULL DEFAULT '0',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DeliveryAssignment (backend/domain/orders_delivery/driver.py, §33) ──
    """
    CREATE TABLE IF NOT EXISTS delivery_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        delivery_job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
        driver_id TEXT NOT NULL,
        assigned_by_user_id TEXT NOT NULL,
        vehicle_id TEXT,
        status TEXT NOT NULL DEFAULT 'PROPOSED',
        assigned_at TEXT NOT NULL,
        accepted_at TEXT,
        released_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DeliveryRoute / DeliveryRouteStop (backend/domain/orders_delivery/route.py, §35) ─
    """
    CREATE TABLE IF NOT EXISTS delivery_routes (
        id TEXT NOT NULL PRIMARY KEY,
        branch_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        assigned_driver_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delivery_route_stops (
        id TEXT NOT NULL PRIMARY KEY,
        route_id TEXT NOT NULL REFERENCES delivery_routes(id),
        delivery_job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
        sequence INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        estimated_arrival_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(route_id, sequence)
    )
    """,
    # ── RedeliveryRequest (backend/domain/orders_delivery/redelivery.py, §41) ─
    """
    CREATE TABLE IF NOT EXISTS redelivery_requests (
        id TEXT NOT NULL PRIMARY KEY,
        original_delivery_job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
        reason TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        new_window_start TEXT,
        new_window_end TEXT,
        additional_fee TEXT NOT NULL DEFAULT '0',
        approved_by_user_id TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        new_delivery_job_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DriverCashCollection (backend/domain/orders_delivery/cash_collection.py, §44-45) ─
    """
    CREATE TABLE IF NOT EXISTS driver_cash_collections (
        id TEXT NOT NULL PRIMARY KEY,
        delivery_job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
        driver_id TEXT NOT NULL,
        expected_amount TEXT NOT NULL DEFAULT '0',
        payment_method TEXT NOT NULL,
        collected_amount TEXT NOT NULL DEFAULT '0',
        reference TEXT,
        status TEXT NOT NULL DEFAULT 'EXPECTED',
        collected_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── DriverSettlement (backend/domain/orders_delivery/settlement.py, §46) ─
    """
    CREATE TABLE IF NOT EXISTS driver_settlements (
        id TEXT NOT NULL PRIMARY KEY,
        driver_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        collection_ids_json TEXT NOT NULL DEFAULT '[]',
        expected_total TEXT NOT NULL DEFAULT '0',
        collected_total TEXT NOT NULL DEFAULT '0',
        status TEXT NOT NULL DEFAULT 'OPEN',
        reviewed_by_user_id TEXT,
        approved_by_user_id TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── transactional outbox (§57) ───────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS orders_delivery_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        aggregate_type TEXT NOT NULL,
        aggregate_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING',
        retries INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        next_retry_at TEXT,
        created_at TEXT NOT NULL,
        processed_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_branch ON customer_orders(branch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_customer ON customer_orders(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_status ON customer_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_sale ON customer_orders(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_whatsapp"
    " ON customer_orders(whatsapp_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_orders_schedule"
    " ON customer_orders(schedule_status, activation_at)",
    "CREATE INDEX IF NOT EXISTS idx_customer_order_lines_order ON customer_order_lines(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_order_lines_product"
    " ON customer_order_lines(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_addresses_order ON order_addresses(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_addresses_zone ON order_addresses(delivery_zone_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_zones_branch ON delivery_zones(branch_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_order_packages_order ON order_packages(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_jobs_order ON delivery_jobs(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_jobs_branch_status"
    " ON delivery_jobs(branch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_jobs_driver ON delivery_jobs(assigned_driver_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_attempts_job ON delivery_attempts(delivery_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_driver_profiles_branch"
    " ON driver_operational_profiles(branch_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_assignments_job"
    " ON delivery_assignments(delivery_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_assignments_driver"
    " ON delivery_assignments(driver_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_branch"
    " ON delivery_routes(branch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_route_stops_route"
    " ON delivery_route_stops(route_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_route_stops_job"
    " ON delivery_route_stops(delivery_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_redelivery_requests_job"
    " ON redelivery_requests(original_delivery_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_redelivery_requests_status"
    " ON redelivery_requests(status)",
    "CREATE INDEX IF NOT EXISTS idx_driver_cash_collections_job"
    " ON driver_cash_collections(delivery_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_driver_cash_collections_driver"
    " ON driver_cash_collections(driver_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_driver_settlements_driver"
    " ON driver_settlements(driver_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_order_lines_package"
    " ON customer_order_lines(package_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_delivery_outbox_status"
    " ON orders_delivery_outbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_delivery_outbox_aggregate"
    " ON orders_delivery_outbox(aggregate_type, aggregate_id)",
)


def create_orders_delivery_schema(conn) -> None:
    """Create the canonical Pedidos/Delivery schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_orders_delivery_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(ORDERS_DELIVERY_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
