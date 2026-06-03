from __future__ import annotations

from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator


def run(conn) -> None:
    DeliverySchemaMigrator(conn).ensure_schema()
