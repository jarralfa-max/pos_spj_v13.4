# ORD-3 — Esquema limpio (Pedidos/Delivery)

Fecha: 2026-08-29. Alcance: master prompt §9.3 (schema), §57 (outbox), §58 (idempotencia).

## Qué se construyó

- `backend/infrastructure/db/schema/orders_delivery_schema.py` —
  `create_orders_delivery_schema()`/`drop_orders_delivery_schema()`, mirror exacto de
  `loyalty_schema.py` (LOY-3). Tablas nuevas: `customer_orders`, `customer_order_lines`,
  `orders_delivery_outbox`.
- `migrations/standalone/226_orders_delivery_bounded_context_schema.py`, registrada en
  `migrations/engine.py` y documentada en `MIGRATION_LOG.md`.
- 7 tests (`tests/unit/test_orders_delivery_schema.py`): tablas creadas, idempotencia,
  `UNIQUE(operation_id)` en `customer_orders`/`orders_delivery_outbox`,
  `UNIQUE(channel, external_order_reference)` (dedup §18), drop limpio, sin colisión con
  tablas legacy.

## Decisiones

- **Sin colisión de nombres** (a diferencia de la colisión real que LOY-3 tuvo con
  `loyalty_programs`): verificado por grep antes de nombrar — `customer_orders`/
  `customer_order_lines`/`orders_delivery_outbox` no existen en ningún otro lado.
- **`customer_orders.customer_id` apunta a `customers` (UUIDv7) lógicamente, nunca a
  `clientes` legacy** — mismo precedente que `loyalty_accounts.customer_id`. El puente de
  identidad legacy (ORD-0 §4.1) sigue abierto solo para el código EXISTENTE de
  `core/delivery/`.
- **Decimal-as-TEXT, sin CHECK de enum** — mismo criterio que `sales_schema.py`/
  `loyalty_schema.py`: la capa de dominio ya construida en ORD-2 es la única fuente de
  verdad de transiciones válidas.
- Las tablas legacy (`delivery_orders`, `delivery_items`, `pedidos_whatsapp`, etc.) NO se
  tocan — siguen siendo la fuente real para `core/delivery/`/`modulos/delivery.py`. La
  triplicación de dueño de esquema que ORD-0 §3 encontró (093/094/095.sql stale vs.
  `DeliverySchemaMigrator`) sigue sin resolverse; es un problema del esquema LEGACY, no del
  nuevo — se aborda en ORD-29 (eliminación de legacy), no aquí.

## Pendiente

- Repositorios/UoW para persistir `CustomerOrder`/`CustomerOrderLine` (no construidos en
  esta fase — ORD-5+ los necesitará al construir los primeros Use Cases).
