"""Durable approvals for supplier-origin loading variances."""


def run(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS logistics_loading_authorizations (
            id TEXT NOT NULL PRIMARY KEY,
            shipment_id TEXT NOT NULL REFERENCES logistics_shipments(id),
            source_line_id TEXT NOT NULL,
            authorized_by_user_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            UNIQUE(shipment_id, source_line_id)
        )""")
    connection.commit()


up = run
