"""Shared blind-count visibility guards for operational cash read models."""

from __future__ import annotations


def shift_has_open_blind_count(connection, shift_id: str) -> bool:
    try:
        row = connection.execute(
            "SELECT 1 FROM cash_counts WHERE shift_id=? AND status='OPEN' LIMIT 1",
            (shift_id,),
        ).fetchone()
    except AttributeError:
        return False
    return row is not None


def branch_has_open_blind_count(connection, branch_id: str) -> bool:
    try:
        row = connection.execute(
            """SELECT 1
               FROM cash_counts c
               JOIN cash_shifts s ON s.id=c.shift_id
               WHERE c.branch_id=? AND s.branch_id=? AND c.status='OPEN'
               LIMIT 1""",
            (branch_id, branch_id),
        ).fetchone()
    except AttributeError:
        return False
    return row is not None
