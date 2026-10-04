"""Reglas de acumulación (§13) y combinación de beneficios (§24), 2026-10-03.

* ``loyalty_rules`` — la regla declarativa; definiciones y alcances en JSON
  validado por el dominio (`LoyaltyRule`), nunca código.
* ``loyalty_sale_evaluations`` — una fila por compra evaluada: cuántos puntos
  dio y con qué reglas (el desglose que se le puede explicar al cliente) y la
  fecha de la visita (primera compra, frecuencia).
* ``loyalty_rule_applications`` — cada regla aplicada a cada compra: cuenta
  los límites (usos totales, por cliente, por día, por mes).
* ``loyalty_stacking_rules`` — qué hacer con cada combinación de beneficios.
* ``loyalty_reward_products`` — qué producto (y cuánto) entrega una recompensa
  de tipo PRODUCTO; ``loyalty_reward_deliveries`` — la salida de inventario de
  cada entrega, con su costo (2026-10-03, migración 297).
"""

from __future__ import annotations

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS loyalty_rules (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        rule_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        priority INTEGER NOT NULL DEFAULT 100,
        program_id TEXT,
        condition_definition TEXT NOT NULL DEFAULT '{}',
        benefit_definition TEXT NOT NULL DEFAULT '{}',
        effective_from TEXT,
        effective_to TEXT,
        stackable INTEGER NOT NULL DEFAULT 1,
        maximum_uses INTEGER,
        customer_limit INTEGER,
        daily_limit INTEGER,
        monthly_limit INTEGER,
        branch_scope TEXT NOT NULL DEFAULT '[]',
        channel_scope TEXT NOT NULL DEFAULT '[]',
        payment_method_scope TEXT NOT NULL DEFAULT '[]',
        product_scope TEXT NOT NULL DEFAULT '[]',
        category_scope TEXT NOT NULL DEFAULT '[]',
        customer_segment_scope TEXT NOT NULL DEFAULT '[]',
        created_by_user_id TEXT NOT NULL,
        activated_by_user_id TEXT,
        activated_at TEXT,
        deactivated_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_rules_status ON loyalty_rules (status, priority)",
    """
    CREATE TABLE IF NOT EXISTS loyalty_sale_evaluations (
        sale_id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        loyalty_account_id TEXT,
        points TEXT NOT NULL DEFAULT '0',
        breakdown_json TEXT NOT NULL DEFAULT '[]',
        evaluated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_sale_evaluations_customer"
    " ON loyalty_sale_evaluations (customer_id, evaluated_at)",
    """
    CREATE TABLE IF NOT EXISTS loyalty_rule_applications (
        id TEXT NOT NULL PRIMARY KEY,
        rule_id TEXT NOT NULL REFERENCES loyalty_rules(id),
        sale_id TEXT NOT NULL,
        customer_id TEXT,
        points TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        UNIQUE (rule_id, sale_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_rule_applications_customer"
    " ON loyalty_rule_applications (rule_id, customer_id, applied_at)",
    """
    CREATE TABLE IF NOT EXISTS loyalty_reward_products (
        reward_id TEXT NOT NULL PRIMARY KEY,
        product_id TEXT NOT NULL,
        quantity TEXT NOT NULL DEFAULT '1'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loyalty_reward_deliveries (
        redemption_id TEXT NOT NULL PRIMARY KEY,
        reward_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit_cost TEXT,
        cost_amount TEXT NOT NULL DEFAULT '0',
        inventory_operation_id TEXT NOT NULL,
        delivered_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loyalty_birthday_grants (
        program_id TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        year TEXT NOT NULL,   -- TEXT: ninguna columna de llave primaria es entera (REGLA CERO)
        granted_at TEXT NOT NULL,
        PRIMARY KEY (program_id, customer_id, year)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loyalty_stacking_rules (
        combination TEXT NOT NULL PRIMARY KEY,
        option TEXT NOT NULL DEFAULT 'ALLOW',
        limit_value TEXT,
        priority_order TEXT NOT NULL DEFAULT '[]',
        updated_by_user_id TEXT,
        updated_at TEXT NOT NULL
    )
    """,
)


def create_loyalty_rules_schema(connection) -> None:
    for ddl in _DDL:
        connection.execute(ddl)


__all__ = ["create_loyalty_rules_schema"]
