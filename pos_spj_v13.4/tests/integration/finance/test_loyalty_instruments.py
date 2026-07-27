"""FASE 15 — fidelidad: emisión, canje, expiración, reverso, idempotencia (§27)."""

import pytest

from backend.application.event_handlers.finance.loyalty_points_expired_handler import (
    LoyaltyPointsExpiredHandler,
)
from backend.application.event_handlers.finance.loyalty_points_issued_handler import (
    LoyaltyPointsIssuedHandler,
)
from backend.application.event_handlers.finance.loyalty_points_redeemed_handler import (
    LoyaltyPointsRedeemedHandler,
)
from backend.application.event_handlers.finance.loyalty_reward_granted_handler import (
    LoyaltyRewardGrantedHandler,
)
from backend.application.event_handlers.finance.loyalty_transaction_reversed_handler import (
    LoyaltyTransactionReversedHandler,
)
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
    JournalEntryStatus,
)
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    ObligationStateError,
    PostingProfileNotFoundError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

OCCURRED = "2026-07-16T12:00:00Z"


def _issue_payload(**overrides):
    payload = {
        "event_id": new_uuid(), "operation_id": new_uuid(),
        "customer_id": new_uuid(), "branch_id": new_uuid(),
        "sale_id": new_uuid(), "loyalty_transaction_id": new_uuid(),
        "points": "100", "estimated_fair_value": "10.00",
        "currency_code": "MXN", "occurred_at": OCCURRED,
    }
    payload.update(overrides)
    return payload


def _obligation(conn, transaction_id):
    with FinanceUnitOfWork(conn) as uow:
        return uow.commercial_obligations.find_by_instrument(
            CommercialInstrumentType.LOYALTY_POINTS, transaction_id)


class TestPointsIssue:
    def test_issue_recognizes_obligation_and_posts(self, bootstrapped_conn):
        payload = _issue_payload()
        LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
        obligation = _obligation(bootstrapped_conn, payload["loyalty_transaction_id"])
        assert obligation is not None
        assert obligation.status is CommercialObligationStatus.OPEN
        assert obligation.outstanding_amount.to_string() == "10.00"
        entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_RECOGNITION'"
        ).fetchone()[0]
        assert entries == 1

    def test_repeated_event_is_idempotent(self, bootstrapped_conn):
        payload = _issue_payload()
        handler = LoyaltyPointsIssuedHandler(bootstrapped_conn)
        handler.handle(payload)
        handler.handle(payload)
        handler.handle(_issue_payload(
            loyalty_transaction_id=payload["loyalty_transaction_id"]))
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM commercial_obligations").fetchone()[0]
        assert count == 1

    def test_missing_profile_blocks_processing(self, finance_conn):
        """Programa sin perfil contable: el evento falla explícitamente."""
        payload = _issue_payload()
        with pytest.raises(PostingProfileNotFoundError):
            LoyaltyPointsIssuedHandler(finance_conn).handle(payload)


class TestPointsRedemption:
    def _issued(self, conn, value="10.00"):
        payload = _issue_payload(estimated_fair_value=value)
        LoyaltyPointsIssuedHandler(conn).handle(payload)
        return payload["loyalty_transaction_id"]

    def test_partial_then_total_redemption(self, bootstrapped_conn):
        transaction_id = self._issued(bootstrapped_conn)
        handler = LoyaltyPointsRedeemedHandler(bootstrapped_conn)
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": transaction_id, "occurred_at": OCCURRED,
            "redeemed_value": "4.00", "loyalty_redemption_id": new_uuid(),
        })
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.PARTIALLY_REDEEMED
        assert obligation.outstanding_amount.to_string() == "6.00"

        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": transaction_id, "occurred_at": OCCURRED,
            "redeemed_value": "6.00", "loyalty_redemption_id": new_uuid(),
        })
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.status is CommercialObligationStatus.REDEEMED

    def test_estimation_vs_actual_cost_difference(self, bootstrapped_conn):
        transaction_id = self._issued(bootstrapped_conn)
        LoyaltyPointsRedeemedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": transaction_id, "occurred_at": OCCURRED,
            "redeemed_value": "10.00", "actual_reward_cost": "8.40",
            "loyalty_redemption_id": new_uuid(),
        })
        # entry must remain balanced with the 1.60 breakage difference
        rows = bootstrapped_conn.execute(
            "SELECT SUM(CAST(debit_amount AS NUMERIC)), SUM(CAST(credit_amount AS NUMERIC))"
            " FROM journal_lines").fetchone()
        assert rows[0] == rows[1]

    def test_double_redemption_event_no_duplicate(self, bootstrapped_conn):
        transaction_id = self._issued(bootstrapped_conn)
        redemption_id = new_uuid()
        event = {
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": transaction_id, "occurred_at": OCCURRED,
            "redeemed_value": "10.00", "loyalty_redemption_id": redemption_id,
        }
        handler = LoyaltyPointsRedeemedHandler(bootstrapped_conn)
        handler.handle(event)
        handler.handle(event)  # same event id
        handler.handle({**event, "event_id": new_uuid(), "operation_id": new_uuid()})
        obligation = _obligation(bootstrapped_conn, transaction_id)
        assert obligation.redeemed_amount.to_string() == "10.00"


class TestPointsExpiration:
    def test_expiration_releases_with_trace(self, bootstrapped_conn):
        payload = _issue_payload()
        LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
        LoyaltyPointsExpiredHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": payload["loyalty_transaction_id"],
            "occurred_at": OCCURRED,
        })
        obligation = _obligation(bootstrapped_conn, payload["loyalty_transaction_id"])
        assert obligation.status is CommercialObligationStatus.EXPIRED
        assert obligation.outstanding_amount.is_zero()
        expiration_entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_EXPIRATION'"
        ).fetchone()[0]
        assert expiration_entries == 1  # nunca se borra en silencio

    def test_double_expiration_no_duplicate(self, bootstrapped_conn):
        payload = _issue_payload()
        LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
        handler = LoyaltyPointsExpiredHandler(bootstrapped_conn)
        event = {
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": payload["loyalty_transaction_id"],
            "occurred_at": OCCURRED,
        }
        handler.handle(event)
        handler.handle({**event, "event_id": new_uuid(), "operation_id": new_uuid()})
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='INSTRUMENT_EXPIRATION'"
        ).fetchone()[0]
        assert count == 1


class TestPointsReversal:
    def test_reversal_mirrors_recognition(self, bootstrapped_conn):
        payload = _issue_payload()
        LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
        LoyaltyTransactionReversedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": payload["loyalty_transaction_id"],
            "occurred_at": OCCURRED, "reason": "venta cancelada",
        })
        obligation = _obligation(bootstrapped_conn, payload["loyalty_transaction_id"])
        assert obligation.status is CommercialObligationStatus.REVERSED
        statuses = {row[0] for row in bootstrapped_conn.execute(
            "SELECT status FROM journal_entries")}
        assert JournalEntryStatus.REVERSED.value in statuses

    def test_double_reversal_rejected(self, bootstrapped_conn):
        payload = _issue_payload()
        LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
        handler = LoyaltyTransactionReversedHandler(bootstrapped_conn)
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "loyalty_transaction_id": payload["loyalty_transaction_id"],
            "occurred_at": OCCURRED,
        })
        with pytest.raises(ObligationStateError):
            handler.handle({
                "event_id": new_uuid(), "operation_id": new_uuid(),
                "loyalty_transaction_id": payload["loyalty_transaction_id"],
                "occurred_at": OCCURRED,
            })


class TestRewardGranted:
    def test_reward_posts_expense(self, bootstrapped_conn):
        LoyaltyRewardGrantedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "reward_id": new_uuid(), "occurred_at": OCCURRED,
            "reward_cost": "45.00", "delivers_inventory": True,
        })
        row = bootstrapped_conn.execute(
            "SELECT SUM(CAST(debit_amount AS NUMERIC)) FROM journal_lines").fetchone()
        assert float(row[0]) == 45.0

    def test_points_never_monetary_without_valuation(self, bootstrapped_conn):
        """El evento sin estimated_fair_value falla — los puntos no son moneda."""
        payload = _issue_payload()
        del payload["estimated_fair_value"]
        with pytest.raises(FinanceDomainError):
            LoyaltyPointsIssuedHandler(bootstrapped_conn).handle(payload)
