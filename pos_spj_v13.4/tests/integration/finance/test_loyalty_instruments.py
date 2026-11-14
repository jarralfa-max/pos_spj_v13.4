"""FASE 15 — fidelidad: emisión, canje, expiración, reverso, idempotencia (§27).

SDLC-FIN-001: las reglas viven en ``CommercialInstrumentProcessor``, el que usa el
puente de Fidelidad. Dos pruebas de los manejadores retirados no se migraron
porque su regla ya no existe aparte: el costo de un premio entregado lo cubre
``test_confirming_a_product_reward_issues_stock_and_posts_its_cost`` y la valuación
de los puntos ``test_accrual_recognizes_liability_at_point_value``.
"""

from datetime import date

import pytest

from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
    JournalEntryStatus,
)
from backend.domain.finance.exceptions import ObligationStateError, PostingProfileNotFoundError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

ON = date(2026, 7, 16)
POINTS = CommercialInstrumentType.LOYALTY_POINTS


def _issue(conn, transaction_id=None, value="10.00"):
    transaction_id = transaction_id or new_uuid()
    with FinanceUnitOfWork(conn) as uow:
        CommercialInstrumentProcessor().recognize(
            uow, instrument_type=POINTS, source_module="loyalty",
            source_instrument_id=transaction_id, amount=Money.from_string(value), on_date=ON,
            operation_id=new_uuid(), customer_id=new_uuid(), branch_id=new_uuid())
    return transaction_id


def _redeem(conn, transaction_id, value, **extra):
    with FinanceUnitOfWork(conn) as uow:
        CommercialInstrumentProcessor().redeem(
            uow, instrument_type=POINTS, source_instrument_id=transaction_id,
            amount=Money.from_string(value), on_date=ON, operation_id=new_uuid(), **extra)


def _expire(conn, transaction_id):
    with FinanceUnitOfWork(conn) as uow:
        CommercialInstrumentProcessor().expire(
            uow, instrument_type=POINTS, source_instrument_id=transaction_id, on_date=ON,
            operation_id=new_uuid())


def _reverse(conn, transaction_id):
    with FinanceUnitOfWork(conn) as uow:
        CommercialInstrumentProcessor().reverse(
            uow, instrument_type=POINTS, source_instrument_id=transaction_id, on_date=ON,
            operation_id=new_uuid(), reason="venta cancelada")


def _obligation(conn, transaction_id):
    with FinanceUnitOfWork(conn) as uow:
        return uow.commercial_obligations.find_by_instrument(POINTS, transaction_id)


class TestPointsIssue:
    def test_issue_recognizes_obligation_and_posts(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation is not None
        assert obligation.status is CommercialObligationStatus.OPEN
        assert obligation.outstanding_amount.to_string() == "10.00"
        entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_RECOGNITION'"
        ).fetchone()[0]
        assert entries == 1

    def test_repeated_recognition_is_idempotent(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _issue(bootstrapped_conn, transaction_id)
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM commercial_obligations").fetchone()[0]
        assert count == 1

    def test_missing_profile_blocks_processing(self, finance_conn):
        """Programa sin perfil contable: falla explícitamente."""
        with pytest.raises(PostingProfileNotFoundError):
            _issue(finance_conn)


class TestPointsRedemption:
    def test_partial_then_total_redemption(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _redeem(bootstrapped_conn, transaction_id, "4.00", redemption_id=new_uuid())
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.PARTIALLY_REDEEMED
        assert obligation.outstanding_amount.to_string() == "6.00"

        _redeem(bootstrapped_conn, transaction_id, "6.00", redemption_id=new_uuid())
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.REDEEMED

    def test_estimation_vs_actual_cost_difference(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _redeem(bootstrapped_conn, transaction_id, "10.00", redemption_id=new_uuid(),
                actual_cost=Money.from_string("8.40"))
        # entry must remain balanced with the 1.60 breakage difference
        rows = bootstrapped_conn.execute(
            "SELECT SUM(CAST(debit_amount AS NUMERIC)), SUM(CAST(credit_amount AS NUMERIC))"
            " FROM journal_lines").fetchone()
        assert rows[0] == rows[1]

    def test_double_redemption_no_duplicate(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        redemption_id = new_uuid()
        _redeem(bootstrapped_conn, transaction_id, "10.00", redemption_id=redemption_id)
        _redeem(bootstrapped_conn, transaction_id, "10.00", redemption_id=redemption_id)
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.redeemed_amount.to_string() == "10.00"


class TestPointsExpiration:
    def test_expiration_releases_with_trace(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _expire(bootstrapped_conn, transaction_id)
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.EXPIRED
        assert obligation.outstanding_amount.is_zero()
        expiration_entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_EXPIRATION'"
        ).fetchone()[0]
        assert expiration_entries == 1  # nunca se borra en silencio

    def test_double_expiration_no_duplicate(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _expire(bootstrapped_conn, transaction_id)
        _expire(bootstrapped_conn, transaction_id)
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_EXPIRATION'"
        ).fetchone()[0]
        assert count == 1


class TestPointsReversal:
    def test_reversal_mirrors_recognition(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _reverse(bootstrapped_conn, transaction_id)
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.REVERSED
        statuses = {row[0] for row in bootstrapped_conn.execute(
            "SELECT status FROM journal_entries")}
        assert JournalEntryStatus.REVERSED.value in statuses

    def test_double_reversal_rejected(self, bootstrapped_conn):
        transaction_id = _issue(bootstrapped_conn)
        _reverse(bootstrapped_conn, transaction_id)
        with pytest.raises(ObligationStateError):
            _reverse(bootstrapped_conn, transaction_id)
