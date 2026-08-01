"""Durable metadata linking mobile photo evidence to shipment assignments."""


def run(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS logistics_shipment_photos (
            id TEXT NOT NULL PRIMARY KEY,
            shipment_id TEXT NOT NULL REFERENCES logistics_shipments(id),
            assignment_id TEXT NOT NULL REFERENCES logistics_shipment_contents(id),
            file_name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            actor_user_id TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )""")
    connection.commit()


up = run
