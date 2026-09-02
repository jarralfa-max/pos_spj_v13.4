"""SET-16 cutover — `DocumentSequenceRepository.next_number()` against a
real procurement schema (`proc_conn`, now includes migration 216's
document-numbering schema — see `conftest.py`). Confirms: bootstrap from
pre-existing legacy rows never collides with already-issued numbers; a
fresh prefix starts at 1; repeated calls reuse the bootstrapped sequence
(no re-scan); output format is byte-identical to the pre-cutover
implementation; a concurrent double-bootstrap degrades safely.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.enums import SequenceResetPolicy
from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (
    SqliteDocumentNumberSequenceRepository,
)
from backend.infrastructure.db.repositories.procurement.support_repositories import DocumentSequenceRepository
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _insert_purchase_order(conn, *, document_number: str) -> None:
    conn.execute(
        "INSERT INTO purchase_orders (id, document_number, supplier_id, branch_id, warehouse_id,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (new_uuid(), document_number, new_uuid(), new_uuid(), new_uuid(), _now(), _now()),
    )


class TestNextNumberBootstrap:
    def test_continues_from_existing_legacy_numbers(self, proc_conn):
        for n in range(1, 6):
            _insert_purchase_order(proc_conn, document_number=f"OC-2026-{n:06d}")
        proc_conn.commit()

        repo = DocumentSequenceRepository(proc_conn)
        number = repo.next_number("OC", 2026)

        assert str(number) == "OC-2026-000006"

    def test_fresh_prefix_starts_at_one(self, proc_conn):
        repo = DocumentSequenceRepository(proc_conn)
        number = repo.next_number("REC", 2026)
        assert str(number) == "REC-2026-000001"

    def test_second_call_reuses_the_bootstrapped_sequence_no_rescan(self, proc_conn):
        for n in range(1, 4):
            _insert_purchase_order(proc_conn, document_number=f"OC-2026-{n:06d}")
        proc_conn.commit()

        repo = DocumentSequenceRepository(proc_conn)
        first = repo.next_number("OC", 2026)
        proc_conn.commit()
        # A new legacy row appearing after bootstrap must NOT affect the
        # already-bootstrapped sequence's count — proves it isn't re-scanning.
        _insert_purchase_order(proc_conn, document_number="OC-2026-999999")
        proc_conn.commit()
        second = repo.next_number("OC", 2026)

        assert str(first) == "OC-2026-000004"
        assert str(second) == "OC-2026-000005"

    def test_output_format_matches_the_legacy_scheme_exactly(self, proc_conn):
        repo = DocumentSequenceRepository(proc_conn)
        number = repo.next_number("SC", 2026)
        assert str(number) == "SC-2026-000001"
        assert number.prefix == "SC"
        assert number.year == 2026
        assert number.sequence == 1

    def test_year_advancing_forward_rolls_over_to_a_fresh_period(self, proc_conn):
        """Realistic usage: `_year()` always reflects wall-clock "now", so
        within one sequence's lifetime years only ever advance forward —
        never jump backward mid-session the way this test would need to
        fabricate to exercise a reverse rollover, which is not a real
        scenario `SequenceResetPolicy.YEARLY` needs to support."""
        repo = DocumentSequenceRepository(proc_conn)
        assert str(repo.next_number("OC", 2026)) == "OC-2026-000001"
        assert str(repo.next_number("OC", 2026)) == "OC-2026-000002"
        assert str(repo.next_number("OC", 2027)) == "OC-2027-000001"
        assert str(repo.next_number("OC", 2027)) == "OC-2027-000002"

    def test_unknown_prefix_returns_sequence_one_without_touching_storage(self, proc_conn):
        repo = DocumentSequenceRepository(proc_conn)
        number = repo.next_number("ZZZ", 2026)
        assert str(number) == "ZZZ-2026-000001"
        assert SqliteDocumentNumberSequenceRepository(proc_conn).get_by_prefix("ZZZ") is None

    def test_concurrent_double_bootstrap_degrades_to_a_single_winner(self, proc_conn):
        """Simulates the actual race: this caller's `get_by_prefix()`
        returned None (calling `_bootstrap_sequence` directly, as
        `next_number()` would have at that point), but by the time it
        tries to INSERT, a concurrent process has ALREADY won the
        bootstrap for the same prefix. Confirms the UNIQUE(prefix)
        collision is caught and the winner's row is returned instead of
        raising — never two independent sequences for one prefix."""
        seq_repo = SqliteDocumentNumberSequenceRepository(proc_conn)
        winner = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        winner.period_key = "2026"
        winner.current_value = 10
        seq_repo.save(winner)
        proc_conn.commit()

        repo = DocumentSequenceRepository(proc_conn)
        resolved = repo._bootstrap_sequence(seq_repo, prefix="OC", period_key="2026")

        assert resolved.id == winner.id
        assert resolved.current_value == 10

    def test_next_number_continues_the_bootstrap_winners_counter(self, proc_conn):
        seq_repo = SqliteDocumentNumberSequenceRepository(proc_conn)
        winner = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        winner.period_key = "2026"
        winner.current_value = 10
        seq_repo.save(winner)
        proc_conn.commit()

        repo = DocumentSequenceRepository(proc_conn)
        number = repo.next_number("OC", 2026)

        assert str(number) == "OC-2026-000011"  # continued the WINNER's counter, not a fresh one
