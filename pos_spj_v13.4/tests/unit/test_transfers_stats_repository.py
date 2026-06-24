"""Protection tests for transfer KPI counts extracted from transferencias.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.transfers_stats_repository import (
    TransfersStatsRepository,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE transferencias (id INTEGER PRIMARY KEY, estado TEXT, fecha TEXT);
        INSERT INTO transferencias (estado, fecha) VALUES
            ('DISPATCHED', date('now')),
            ('DISPATCHED', date('now')),
            ('PENDING',    date('now')),
            ('RECEIVED',   date('now')),
            ('RECEIVED',   '2000-01-01'),
            ('CANCELLED',  date('now')),
            ('CANCELLED',  '2000-01-01');
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return TransfersStatsRepository(db)


def test_status_counts(repo):
    counts = repo.get_status_counts()
    assert counts["dispatched"] == 2
    assert counts["pending"] == 1
    # only this-month rows count for received / cancelled
    assert counts["received_this_month"] == 1
    assert counts["cancelled_this_month"] == 1


def test_status_counts_empty(repo, db):
    db.execute("DELETE FROM transferencias")
    db.commit()
    assert repo.get_status_counts() == {
        "dispatched": 0, "received_this_month": 0, "pending": 0, "cancelled_this_month": 0,
    }
