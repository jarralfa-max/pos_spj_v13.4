"""Migration 093 — centralize Delivery schema in DeliverySchemaMigrator.

The migration is Python instead of raw SQL because SQLite does not support
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``; idempotent column backfills are
implemented by the shared migrator.
"""
from __future__ import annotations

import sqlite3

version = 93
description = "delivery schema migrator"


def up(conn: sqlite3.Connection) -> None:
    from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator

    DeliverySchemaMigrator(conn).ensure_schema()


run = up
