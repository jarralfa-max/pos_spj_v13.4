"""CommercialInstrumentsUnitOfWork — one transaction boundary for the
Commercial Instruments context. Mirrors
backend/infrastructure/db/repositories/loyalty/unit_of_work.py's
`LoyaltyUnitOfWork` exactly."""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.commercial_instruments.coupon_repository import (
    CouponDefinitionRepository,
    CouponInstanceRepository,
    CouponRedemptionRepository,
)
from backend.infrastructure.db.repositories.commercial_instruments.outbox_repository import (
    CommercialInstrumentsOutboxRepository,
)
from backend.infrastructure.db.repositories.commercial_instruments.voucher_repository import (
    VoucherDefinitionRepository,
    VoucherInstanceRepository,
    VoucherRedemptionRepository,
    VoucherTransactionRepository,
)


class CommercialInstrumentsUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.coupon_definitions = CouponDefinitionRepository(connection)
        self.coupon_instances = CouponInstanceRepository(connection)
        self.coupon_redemptions = CouponRedemptionRepository(connection)
        self.voucher_definitions = VoucherDefinitionRepository(connection)
        self.voucher_instances = VoucherInstanceRepository(connection)
        self.voucher_transactions = VoucherTransactionRepository(connection)
        self.voucher_redemptions = VoucherRedemptionRepository(connection)
        self.outbox = CommercialInstrumentsOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "CommercialInstrumentsUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._owns_transaction:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owns_transaction:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
