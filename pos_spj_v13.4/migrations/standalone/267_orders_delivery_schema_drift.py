"""267 — completa el esquema de Pedidos/Delivery en bases ya migradas.

QUÉ PASABA, MEDIDO (2026-09-18, sobre una copia de la base real)
-----------------------------------------------------------------
La migración 226 crea el esquema llamando a `create_orders_delivery_schema()`.
Esa función siguió creciendo después (paquetes, trabajos de entrega, rutas,
liquidaciones del repartidor, código de verificación de recogida), pero 226 ya
estaba marcada como aplicada y no vuelve a correr — y aunque corriera,
`CREATE TABLE IF NOT EXISTS` no agrega columnas a una tabla que ya existe.

La base real quedó así:

- `customer_orders` sin `pickup_verification_code` y `customer_order_lines`
  sin `package_id`: el repositorio escribe ambas, así que **crear cualquier
  pedido reventaba** ("table customer_orders has no column named
  pickup_verification_code"). "Nuevo pedido" estaba muerto en producción; las
  pruebas no lo veían porque construyen el esquema desde cero.
- 10 tablas inexistentes: `order_packages`, `delivery_jobs`,
  `delivery_attempts`, `driver_operational_profiles`, `delivery_assignments`,
  `delivery_routes`, `delivery_route_stops`, `redelivery_requests`,
  `driver_cash_collections`, `driver_settlements`.

Se midieron TODAS las funciones `create_*_schema` de
`backend/infrastructure/db/schema/` contra la base real: sólo Delivery tenía
deriva.

QUÉ HACE
--------
1. Agrega las columnas que falten (primero: los índices nuevos las usan).
2. Vuelve a correr `create_orders_delivery_schema()`, que crea las tablas e
   índices que falten y no toca lo que ya existe.

Idempotente. No mueve datos.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema

logger = logging.getLogger("spj.migrations.267")

#: (tabla, columna, tipo) que el esquema canónico tiene y 226 no creó.
MISSING_COLUMNS = (
    ("customer_orders", "pickup_verification_code", "TEXT"),
    ("customer_order_lines", "package_id", "TEXT"),
)


def _columns(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def run(conn) -> None:
    agregadas = 0
    for tabla, columna, tipo in MISSING_COLUMNS:
        existentes = _columns(conn, tabla)
        if existentes and columna not in existentes:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
            agregadas += 1
    create_orders_delivery_schema(conn)
    conn.commit()
    logger.info("267: %s columnas agregadas; tablas e índices de Delivery completos.", agregadas)


up = run
