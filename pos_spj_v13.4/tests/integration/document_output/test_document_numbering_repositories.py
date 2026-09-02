"""SET-16 — SqliteDocumentNumberSequenceRepository +
SqliteDocumentNumberReservationRepository against a real (in-memory)
SQLite born-clean schema (migration 216).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.enums import SequenceResetPolicy
from backend.domain.document_output.policies.sequence_reservation_policy import reserve_with_idempotency
from backend.infrastructure.db.repositories.document_output.document_number_reservation_repository import (
    SqliteDocumentNumberReservationRepository,
)
from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (
    SqliteDocumentNumberSequenceRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def sequence_repo(conn):
    return SqliteDocumentNumberSequenceRepository(conn)


@pytest.fixture
def reservation_repo(conn):
    return SqliteDocumentNumberReservationRepository(conn)


class TestSequenceRepository:
    def test_save_get_roundtrip(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence_repo.save(sequence)
        conn.commit()

        fetched = sequence_repo.get(sequence.id)
        assert fetched.prefix == "OC"
        assert fetched.reset_policy is SequenceResetPolicy.YEARLY
        assert fetched.current_value == 0

    def test_get_by_prefix(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC")
        sequence_repo.save(sequence)
        conn.commit()
        assert sequence_repo.get_by_prefix("OC").id == sequence.id
        assert sequence_repo.get_by_prefix("oc").id == sequence.id  # normalized
        assert sequence_repo.get_by_prefix("does-not-exist") is None

    def test_prefix_is_unique(self, conn, sequence_repo):
        sequence_repo.save(DocumentNumberSequence.create(prefix="OC"))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            sequence_repo.save(DocumentNumberSequence.create(prefix="OC"))
            conn.commit()
        conn.rollback()

    def test_upsert_persists_reservations_across_reloads(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence_repo.save(sequence)
        conn.commit()

        sequence.reserve_next(at=datetime(2026, 8, 21, tzinfo=timezone.utc))
        sequence.reserve_next(at=datetime(2026, 8, 22, tzinfo=timezone.utc))
        sequence_repo.save(sequence)
        conn.commit()

        fetched = sequence_repo.get(sequence.id)
        assert fetched.current_value == 2
        assert fetched.period_key == "2026"


class TestReserveAndGetAtomicity:
    """SET-16 cutover — `reserve_and_get()` is the atomic replacement for
    the entity-computes/repo-persists read-modify-write pattern
    `test_upsert_persists_reservations_across_reloads` above exercises;
    this class proves the SQL-level atomicity that pattern can't give."""

    def test_increments_within_the_same_period(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence.period_key = "2026"
        sequence.current_value = 5
        sequence_repo.save(sequence)
        conn.commit()

        assert sequence_repo.reserve_and_get(sequence.id, period_key="2026") == 6
        assert sequence_repo.reserve_and_get(sequence.id, period_key="2026") == 7
        conn.commit()

    def test_rolls_over_to_a_new_period_starting_at_one(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence.period_key = "2026"
        sequence.current_value = 42
        sequence_repo.save(sequence)
        conn.commit()

        assert sequence_repo.reserve_and_get(sequence.id, period_key="2027") == 1
        assert sequence_repo.reserve_and_get(sequence.id, period_key="2027") == 2
        conn.commit()

    def test_persists_across_reloads(self, conn, sequence_repo):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence_repo.save(sequence)
        conn.commit()
        sequence_repo.reserve_and_get(sequence.id, period_key="2026")
        conn.commit()

        fetched = sequence_repo.get(sequence.id)
        assert fetched.current_value == 1
        assert fetched.period_key == "2026"

    def test_concurrent_rollover_never_collides(self, conn, sequence_repo):
        """The concurrency proof: simulate a second writer having ALREADY
        rolled the period over between this caller's read and its
        reservation — the atomic UPDATE's CASE evaluates against the
        row's TRUE current state, not a stale Python-held value, so the
        second reservation correctly lands on 2, never re-lands on a
        colliding 1."""
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence.period_key = "2026"
        sequence.current_value = 99
        sequence_repo.save(sequence)
        conn.commit()

        # Two callers both "decide" (in Python, based on a read taken before
        # either reserves) that the target period is 2027 — the SAME target
        # period_key, not a stale one — exactly what two concurrent workers
        # would compute at a real year boundary.
        first = sequence_repo.reserve_and_get(sequence.id, period_key="2027")
        second = sequence_repo.reserve_and_get(sequence.id, period_key="2027")
        conn.commit()

        assert first == 1
        assert second == 2  # not another 1 — no lost update, no collision


class TestReservationRepositoryIdempotency:
    def test_get_by_operation_id_returns_none_when_absent(self, conn, sequence_repo, reservation_repo):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        sequence_repo.save(sequence)
        conn.commit()
        assert reservation_repo.get_by_operation_id(sequence.id, new_uuid()) is None

    def test_reserve_persist_and_replay_idempotently(self, conn, sequence_repo, reservation_repo):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        sequence_repo.save(sequence)
        conn.commit()

        operation_id = new_uuid()
        existing = reservation_repo.get_by_operation_id(sequence.id, operation_id)
        assert existing is None

        number = reserve_with_idempotency(sequence, existing_reservation=existing)
        sequence_repo.save(sequence)
        reservation_repo.save(sequence.id, operation_id, number)
        conn.commit()
        assert number.sequence_value == 1

        # Simulate a retried request with the same operation_id: must not advance the counter.
        existing_again = reservation_repo.get_by_operation_id(sequence.id, operation_id)
        assert existing_again is not None
        replay = reserve_with_idempotency(sequence, existing_reservation=existing_again)
        assert replay.formatted() == number.formatted()
        assert sequence.current_value == 1  # unchanged by the replay

        # A genuinely new operation still advances.
        next_operation_id = new_uuid()
        next_existing = reservation_repo.get_by_operation_id(sequence.id, next_operation_id)
        assert next_existing is None
        next_number = reserve_with_idempotency(sequence, existing_reservation=next_existing)
        sequence_repo.save(sequence)
        reservation_repo.save(sequence.id, next_operation_id, next_number)
        conn.commit()
        assert next_number.sequence_value == 2

    def test_operation_id_unique_per_sequence_prevents_double_insert(
        self, conn, sequence_repo, reservation_repo,
    ):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        sequence_repo.save(sequence)
        conn.commit()

        operation_id = new_uuid()
        number = sequence.reserve_next()
        reservation_repo.save(sequence.id, operation_id, number)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            reservation_repo.save(sequence.id, operation_id, number)
            conn.commit()
        conn.rollback()

    def test_document_number_is_globally_unique(self, conn, sequence_repo, reservation_repo):
        sequence_a = DocumentNumberSequence.create(prefix="OC")
        sequence_b = DocumentNumberSequence.create(prefix="OC-DUP")
        sequence_repo.save(sequence_a)
        sequence_repo.save(sequence_b)
        conn.commit()

        number = sequence_a.reserve_next()
        reservation_repo.save(sequence_a.id, new_uuid(), number)
        conn.commit()

        # Force a colliding formatted number under a different sequence/operation.
        with pytest.raises(sqlite3.IntegrityError):
            reservation_repo.save(sequence_b.id, new_uuid(), number)
            conn.commit()
        conn.rollback()
