"""FASE 16 — cupones, vales, tarjetas de regalo y saldos promocionales (§27)."""

import pytest

from backend.application.event_handlers.finance.coupon_expired_handler import (
    CouponExpiredHandler,
)
from backend.application.event_handlers.finance.coupon_issued_handler import (
    CouponIssuedHandler,
)
from backend.application.event_handlers.finance.coupon_redeemed_handler import (
    CouponRedeemedHandler,
)
from backend.application.event_handlers.finance.gift_card_redeemed_handler import (
    GiftCardRedeemedHandler,
)
from backend.application.event_handlers.finance.gift_card_refunded_handler import (
    GiftCardRefundedHandler,
)
from backend.application.event_handlers.finance.gift_card_sold_handler import (
    GiftCardSoldHandler,
)
from backend.application.event_handlers.finance.stored_value_adjusted_handler import (
    StoredValueAdjustedHandler,
)
from backend.application.event_handlers.finance.voucher_issued_handler import (
    VoucherIssuedHandler,
)
from backend.application.event_handlers.finance.voucher_redeemed_handler import (
    VoucherRedeemedHandler,
)
from backend.application.services.finance.commercial_reconciliation_service import (
    CommercialReconciliationService,
)
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
)
from backend.domain.finance.exceptions import ObligationAmountError, ObligationStateError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

OCCURRED = "2026-07-16T12:00:00Z"


def _event(**fields):
    base = {"event_id": new_uuid(), "operation_id": new_uuid(),
            "occurred_at": OCCURRED, "currency_code": "MXN"}
    base.update(fields)
    return base


def _get(conn, instrument_type, instrument_id):
    with FinanceUnitOfWork(conn) as uow:
        return uow.commercial_obligations.find_by_instrument(instrument_type, instrument_id)


def _account_id(conn, code):
    with FinanceUnitOfWork(conn) as uow:
        return uow.accounts.get_by_code(code).id


def _lines_for(conn, account_id):
    return conn.execute(
        "SELECT CAST(debit_amount AS NUMERIC), CAST(credit_amount AS NUMERIC)"
        " FROM journal_lines WHERE account_id=?", (account_id,)).fetchall()


class TestPromotionalCoupon:
    def test_issue_creates_no_liability(self, bootstrapped_conn):
        instrument = new_uuid()
        CouponIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="50.00"))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.PROMOTIONAL_COUPON, instrument)
        assert obligation.status is CommercialObligationStatus.PENDING_RECOGNITION
        entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert entries == 0  # promotional coupon: no entry at issuance

    def test_redemption_posts_contra_revenue(self, bootstrapped_conn):
        instrument = new_uuid()
        CouponIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="50.00"))
        CouponRedeemedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, redeemed_value="50.00"))
        contra = _account_id(bootstrapped_conn, "4203")
        rows = _lines_for(bootstrapped_conn, contra)
        assert rows and float(rows[0][0]) == 50.0  # débito a contra-ingreso

    def test_double_redemption_rejected(self, bootstrapped_conn):
        instrument = new_uuid()
        CouponIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="50.00"))
        handler = CouponRedeemedHandler(bootstrapped_conn)
        handler.handle(_event(instrument_id=instrument, redeemed_value="50.00"))
        with pytest.raises(ObligationStateError):
            handler.handle(_event(instrument_id=instrument, redeemed_value="50.00"))

    def test_third_party_funded_coupon_creates_receivable(self, bootstrapped_conn):
        instrument = new_uuid()
        CouponIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="80.00",
                   funding_party="PROVEEDOR-X"))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.PROMOTIONAL_COUPON, instrument)
        assert obligation.recognition_basis.value == "THIRD_PARTY_RECEIVABLE"
        receivable_account = _account_id(bootstrapped_conn, "1135")
        rows = _lines_for(bootstrapped_conn, receivable_account)
        assert rows and float(rows[0][0]) == 80.0

    def test_expiration_of_promotional_coupon_posts_nothing(self, bootstrapped_conn):
        instrument = new_uuid()
        CouponIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="50.00"))
        CouponExpiredHandler(bootstrapped_conn).handle(_event(instrument_id=instrument))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.PROMOTIONAL_COUPON, instrument)
        assert obligation.status is CommercialObligationStatus.EXPIRED
        entries = bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert entries == 0


class TestRefundVoucher:
    def test_issue_creates_real_liability(self, bootstrapped_conn):
        instrument = new_uuid()
        VoucherIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="120.00"))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.REFUND_VOUCHER, instrument)
        assert obligation.status is CommercialObligationStatus.OPEN
        liability = _account_id(bootstrapped_conn, "2132")
        rows = _lines_for(bootstrapped_conn, liability)
        assert rows and float(rows[0][1]) == 120.0  # crédito al pasivo

    def test_partial_and_total_redemption(self, bootstrapped_conn):
        instrument = new_uuid()
        VoucherIssuedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="120.00"))
        handler = VoucherRedeemedHandler(bootstrapped_conn)
        handler.handle(_event(instrument_id=instrument, redeemed_value="70.00",
                              redemption_id=new_uuid()))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.REFUND_VOUCHER, instrument)
        assert obligation.status is CommercialObligationStatus.PARTIALLY_REDEEMED
        handler.handle(_event(instrument_id=instrument, redeemed_value="50.00",
                              redemption_id=new_uuid()))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.REFUND_VOUCHER, instrument)
        assert obligation.status is CommercialObligationStatus.REDEEMED


class TestGiftCard:
    def test_sale_creates_liability_not_revenue(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="500.00"))
        liability = _account_id(bootstrapped_conn, "2131")
        revenue = _account_id(bootstrapped_conn, "4101")
        assert _lines_for(bootstrapped_conn, liability)
        assert not _lines_for(bootstrapped_conn, revenue)  # sin ingreso al vender

    def test_redemption_moves_liability_to_revenue(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="500.00"))
        GiftCardRedeemedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, redeemed_value="200.00",
                   redemption_id=new_uuid()))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.GIFT_CARD, instrument)
        assert obligation.outstanding_amount.to_string() == "300.00"
        revenue = _account_id(bootstrapped_conn, "4101")
        rows = _lines_for(bootstrapped_conn, revenue)
        assert rows and float(rows[0][1]) == 200.0

    def test_over_redemption_rejected(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="100.00"))
        with pytest.raises(ObligationAmountError):
            GiftCardRedeemedHandler(bootstrapped_conn).handle(
                _event(instrument_id=instrument, redeemed_value="150.00",
                       redemption_id=new_uuid()))

    def test_refund_reverses_recognition(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="500.00"))
        GiftCardRefundedHandler(bootstrapped_conn).handle(_event(instrument_id=instrument))
        obligation = _get(bootstrapped_conn, CommercialInstrumentType.GIFT_CARD, instrument)
        assert obligation.status is CommercialObligationStatus.REVERSED
        # ledger neto en cero para el pasivo
        liability = _account_id(bootstrapped_conn, "2131")
        rows = _lines_for(bootstrapped_conn, liability)
        net = sum(float(r[1]) for r in rows) - sum(float(r[0]) for r in rows)
        assert net == 0.0


class TestPromotionalBalance:
    def test_never_recognized_as_cash(self, bootstrapped_conn):
        instrument = new_uuid()
        StoredValueAdjustedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="60.00"))
        for cash_code in ("1101", "1102", "1110"):
            assert not _lines_for(bootstrapped_conn, _account_id(bootstrapped_conn, cash_code))
        promo_liability = _account_id(bootstrapped_conn, "2134")
        assert _lines_for(bootstrapped_conn, promo_liability)

    def test_kept_separate_from_store_credit(self, bootstrapped_conn):
        """Saldo promocional (2134) nunca se mezcla con saldo reembolsable (2133)."""
        instrument = new_uuid()
        StoredValueAdjustedHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="60.00"))
        store_credit = _account_id(bootstrapped_conn, "2133")
        assert not _lines_for(bootstrapped_conn, store_credit)


class TestInstrumentReconciliation:
    def test_matching_balances_report_clean(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="500.00"))
        rows = CommercialReconciliationService().reconcile(
            bootstrapped_conn, {"GIFT_CARD": "500.00"})
        assert rows[0].difference == "0.00" and not rows[0].is_material

    def test_material_difference_emits_event(self, bootstrapped_conn):
        instrument = new_uuid()
        GiftCardSoldHandler(bootstrapped_conn).handle(
            _event(instrument_id=instrument, face_value="500.00"))
        rows = CommercialReconciliationService().reconcile(
            bootstrapped_conn, {"GIFT_CARD": "650.00"})
        assert rows[0].is_material
        events = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox"
            " WHERE event_name='COMMERCIAL_RECONCILIATION_DIFFERENCE_DETECTED'"
        ).fetchone()[0]
        assert events == 1
