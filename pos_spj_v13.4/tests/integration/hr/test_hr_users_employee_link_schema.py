from __future__ import annotations

import sqlite3

from migrations.m000_base_schema import up


def test_users_have_employee_id_uuid_link_column() -> None:
    conn = sqlite3.connect(":memory:")
    up(conn)
    columns = {row[1]: row[2].upper() for row in conn.execute("PRAGMA table_info(usuarios)").fetchall()}
    assert columns["employee_id"] == "TEXT"
