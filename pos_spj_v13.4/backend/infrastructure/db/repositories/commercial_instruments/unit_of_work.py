"""CommercialInstrumentsUnitOfWork — one transaction boundary for the
Commercial Instruments context. Mirrors
backend/infrastructure/db/repositories/loyalty/unit_of_work.py's
`LoyaltyUnitOfWork` exactly."""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.commercial_instruments.batch_repository import (
    InstrumentBatchItemRepository,
    InstrumentBatchRepository,
    VoucherRulesRepository,
)
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
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class CommercialInstrumentsUnitOfWork(TransactionalUnitOfWork):
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
        # Lotes físicos (auditoría de Fidelidad 968e0bc, ampliación).
        self.batches = InstrumentBatchRepository(connection)
        self.batch_items = InstrumentBatchItemRepository(connection)
        self.voucher_rules = VoucherRulesRepository(connection)
        self._completed = False
