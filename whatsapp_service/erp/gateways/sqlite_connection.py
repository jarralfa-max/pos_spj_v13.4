from __future__ import annotations


class ERPSqliteConnection:
    """SQLite connection facade owned by ERPBridge."""

    def __init__(self, bridge):
        self._bridge = bridge

    @property
    def db(self):
        return self._bridge.db
