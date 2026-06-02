-- Fase 9: delivery_order_history es la fuente auditable; historial_cambios queda deprecated.
-- SQLite no soporta ADD COLUMN IF NOT EXISTS en todas las versiones usadas por el POS.
-- La migración ejecutable equivalente es migrations/standalone/095_delivery_history_audit.py,
-- que delega en DeliverySchemaMigrator para agregar columnas de forma idempotente.

CREATE INDEX IF NOT EXISTS idx_delivery_history_order_created
    ON delivery_order_history(order_id, created_at);

CREATE INDEX IF NOT EXISTS idx_delivery_history_event_id
    ON delivery_order_history(event_id);
