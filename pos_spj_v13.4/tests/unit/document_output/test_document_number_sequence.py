"""SET-16 — "Sequences"/"Reservas"/"Reset": DocumentNumberSequence +
DocumentNumber. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.enums import SequenceResetPolicy
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_number import DocumentNumber
from backend.shared.ids import is_uuidv7


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


class TestDocumentNumberCreate:
    def test_requires_prefix(self):
        with pytest.raises(DocumentInvalidValueError):
            DocumentNumber.create(prefix="   ", period_key="2026", sequence_value=1)

    @pytest.mark.parametrize("value", [0, -1, 1.5, True])
    def test_rejects_invalid_sequence_value(self, value):
        with pytest.raises(DocumentInvalidValueError):
            DocumentNumber.create(prefix="OC", period_key="2026", sequence_value=value)

    def test_formatted_with_period(self):
        number = DocumentNumber.create(prefix="OC", period_key="2026", sequence_value=42)
        assert number.formatted() == "OC-2026-000042"
        assert str(number) == "OC-2026-000042"

    def test_formatted_without_period(self):
        number = DocumentNumber.create(prefix="SALE_TICKET", period_key="", sequence_value=7)
        assert number.formatted() == "SALE_TICKET-000007"


class TestDocumentNumberSequenceCreate:
    def test_mints_uuidv7_and_normalizes_prefix(self):
        sequence = DocumentNumberSequence.create(prefix="  oc  ")
        assert is_uuidv7(sequence.id)
        assert sequence.prefix == "OC"
        assert sequence.current_value == 0
        assert sequence.reset_policy is SequenceResetPolicy.NEVER

    def test_requires_prefix(self):
        with pytest.raises(DocumentInvalidValueError):
            DocumentNumberSequence.create(prefix="   ")


class TestReserveNextNeverResets:
    def test_increments_forever_without_period(self):
        sequence = DocumentNumberSequence.create(prefix="SALE_TICKET")
        first = sequence.reserve_next(at=_dt(2026, 1, 1))
        second = sequence.reserve_next(at=_dt(2027, 1, 1))
        assert first.sequence_value == 1
        assert second.sequence_value == 2
        assert first.period_key == ""
        assert second.period_key == ""


class TestReserveNextYearly:
    def test_resets_when_year_changes(self):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        first = sequence.reserve_next(at=_dt(2026, 8, 21))
        second = sequence.reserve_next(at=_dt(2026, 12, 31))
        third = sequence.reserve_next(at=_dt(2027, 1, 1))
        assert (first.period_key, first.sequence_value) == ("2026", 1)
        assert (second.period_key, second.sequence_value) == ("2026", 2)
        assert (third.period_key, third.sequence_value) == ("2027", 1)


class TestReserveNextMonthly:
    def test_resets_when_month_changes(self):
        sequence = DocumentNumberSequence.create(prefix="REC", reset_policy=SequenceResetPolicy.MONTHLY)
        first = sequence.reserve_next(at=_dt(2026, 8, 1))
        second = sequence.reserve_next(at=_dt(2026, 8, 31))
        third = sequence.reserve_next(at=_dt(2026, 9, 1))
        assert (first.period_key, first.sequence_value) == ("2026-08", 1)
        assert (second.period_key, second.sequence_value) == ("2026-08", 2)
        assert (third.period_key, third.sequence_value) == ("2026-09", 1)


class TestReserveNextDaily:
    def test_resets_when_day_changes(self):
        sequence = DocumentNumberSequence.create(prefix="XREPORT", reset_policy=SequenceResetPolicy.DAILY)
        first = sequence.reserve_next(at=_dt(2026, 8, 21))
        second = sequence.reserve_next(at=_dt(2026, 8, 22))
        assert (first.period_key, first.sequence_value) == ("2026-08-21", 1)
        assert (second.period_key, second.sequence_value) == ("2026-08-22", 1)


class TestForceReset:
    def test_resets_current_value_and_period_regardless_of_reset_policy(self):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.NEVER)
        sequence.reserve_next(at=_dt(2026, 1, 1))
        sequence.reserve_next(at=_dt(2026, 1, 2))
        assert sequence.current_value == 2

        sequence.force_reset(period_key="2026-CORRECTED")
        assert sequence.current_value == 0
        assert sequence.period_key == "2026-CORRECTED"

        after = sequence.reserve_next(at=_dt(2026, 1, 3))
        assert after.sequence_value == 1
        assert after.period_key == "2026-CORRECTED"

    def test_force_reset_default_clears_period_key(self):
        sequence = DocumentNumberSequence.create(prefix="OC", reset_policy=SequenceResetPolicy.YEARLY)
        sequence.reserve_next(at=_dt(2026, 1, 1))
        sequence.force_reset()
        assert sequence.period_key == ""
        assert sequence.current_value == 0
