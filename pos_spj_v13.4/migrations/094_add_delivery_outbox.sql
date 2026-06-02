CREATE TABLE IF NOT EXISTS delivery_outbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    aggregate_type TEXT DEFAULT 'delivery_order',
    aggregate_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retries INTEGER DEFAULT 0,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME,
    operation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_delivery_outbox_pending
    ON delivery_outbox_events(status, id);
CREATE INDEX IF NOT EXISTS idx_delivery_outbox_aggregate
    ON delivery_outbox_events(aggregate_type, aggregate_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_outbox_operation
    ON delivery_outbox_events(event_type, aggregate_id, operation_id)
    WHERE operation_id IS NOT NULL;
