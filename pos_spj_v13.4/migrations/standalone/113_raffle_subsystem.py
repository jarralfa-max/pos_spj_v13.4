"""Migración 113 — Subsistema de rifas/sorteos (born-clean UUIDv7).

Centraliza el esquema que LoyaltyRepository.ensure_raffle_tables() creaba ad-hoc
(REGLA 11: el schema vive en migrations/, no en repositorios). Todas las
identidades son UUIDv7 TEXT y las FK funcionales son TEXT; sin DEFAULT 1.
"""

VERSION = "113"
DESCRIPTION = "Subsistema de rifas (UUIDv7 born-clean)"


def run(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS raffles(
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            premio TEXT DEFAULT '',
            premio_costo_estimado REAL DEFAULT 0,
            presupuesto_maximo REAL DEFAULT 0,
            ventas_objetivo REAL DEFAULT 0,
            roi_objetivo REAL DEFAULT 0,
            monto_por_boleto REAL DEFAULT 0,
            max_boletos_por_cliente INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'borrador',
            financial_status TEXT DEFAULT 'presupuestada',
            fecha_inicio TEXT,
            fecha_fin TEXT,
            sucursal_id TEXT,
            created_by TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS raffle_tickets(
            id TEXT PRIMARY KEY,
            raffle_id TEXT NOT NULL,
            cliente_id TEXT,
            venta_id TEXT,
            folio_venta TEXT,
            numero_boleto TEXT NOT NULL,
            monto_base REAL DEFAULT 0,
            estado TEXT DEFAULT 'vigente',
            cancel_reason TEXT DEFAULT '',
            sucursal_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            cancelled_at TEXT,
            UNIQUE(raffle_id, numero_boleto),
            UNIQUE(raffle_id, venta_id, numero_boleto)
        );
        CREATE TABLE IF NOT EXISTS raffle_financial_ledger(
            id TEXT PRIMARY KEY,
            raffle_id TEXT NOT NULL,
            tipo TEXT NOT NULL,
            monto REAL DEFAULT 0,
            referencia TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            usuario TEXT DEFAULT '',
            sucursal_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(raffle_id, tipo, referencia)
        );
        CREATE TABLE IF NOT EXISTS raffle_winners(
            id TEXT PRIMARY KEY,
            raffle_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            prize_id TEXT,
            cliente_id TEXT,
            premio TEXT DEFAULT '',
            premio_costo_real REAL DEFAULT 0,
            estado_entrega TEXT DEFAULT 'pendiente',
            seleccionado_por TEXT DEFAULT '',
            random_seed TEXT DEFAULT '',
            pool_hash TEXT DEFAULT '',
            fecha_seleccion TEXT DEFAULT (datetime('now')),
            fecha_entrega TEXT,
            notificado INTEGER DEFAULT 0,
            UNIQUE(raffle_id, ticket_id)
        );
        CREATE TABLE IF NOT EXISTS raffle_rules(
            id TEXT PRIMARY KEY,
            raffle_id TEXT NOT NULL UNIQUE,
            requires_registered_customer INTEGER DEFAULT 0,
            min_sale_amount REAL DEFAULT 0,
            ticket_strategy TEXT DEFAULT 'per_amount',
            amount_per_ticket REAL DEFAULT 0,
            tickets_per_sale INTEGER DEFAULT 1,
            max_tickets_per_sale INTEGER DEFAULT 0,
            max_tickets_per_customer INTEGER DEFAULT 0,
            include_discounted_sales INTEGER DEFAULT 1,
            allowed_payment_methods TEXT DEFAULT '',
            allowed_weekdays TEXT DEFAULT '',
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS raffle_prizes(
            id TEXT PRIMARY KEY,
            raffle_id TEXT NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            cantidad INTEGER DEFAULT 1,
            costo_estimado REAL DEFAULT 0,
            costo_real REAL DEFAULT 0,
            orden INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'pendiente',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS raffle_eligible_products(
            id TEXT PRIMARY KEY, raffle_id TEXT NOT NULL, product_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS raffle_eligible_categories(
            id TEXT PRIMARY KEY, raffle_id TEXT NOT NULL, category_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS raffle_eligible_branches(
            id TEXT PRIMARY KEY, raffle_id TEXT NOT NULL, sucursal_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_raffles_estado_fecha ON raffles(estado, created_at);
        CREATE INDEX IF NOT EXISTS idx_raffle_tickets_raffle ON raffle_tickets(raffle_id, estado);
        CREATE INDEX IF NOT EXISTS idx_raffle_winners_raffle ON raffle_winners(raffle_id, estado_entrega);
        """
    )
