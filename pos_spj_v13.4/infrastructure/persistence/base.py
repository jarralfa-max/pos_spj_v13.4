# infrastructure/persistence/base.py — SPJ ERP v13.4
"""Abstract base for all SQLite repository implementations."""
from __future__ import annotations

import sqlite3
from abc import ABC
from typing import Any, Dict, List, Optional, Tuple


class BaseRepository(ABC):
    """
    Base class for SQLite repositories in the infrastructure layer.

    Wraps a raw sqlite3 connection with typed helpers so concrete
    repositories never touch low-level cursor management.

    All repositories must receive the connection via __init__ (dependency
    injection from AppContainer) — no singleton or global state here.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Query helpers ─────────────────────────────────────────────────────────

    def _fetchone(self, sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        return cur.fetchone()

    def _fetchall(self, sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def _execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def _executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        return self._conn.executemany(sql, params_seq)

    def _lastrowid(self, sql: str, params: Tuple = ()) -> int:
        cur = self._conn.execute(sql, params)
        return cur.lastrowid
