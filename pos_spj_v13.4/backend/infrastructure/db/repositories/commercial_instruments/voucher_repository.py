"""VoucherDefinitionRepository / VoucherInstanceRepository /
VoucherTransactionRepository / VoucherRedemptionRepository (LOY-13, §22).

`VoucherTransactionRepository.save()`'s `ON CONFLICT` clause only touches
`status`/`reversal_transaction_id` — same append-only guarantee as
`LoyaltyTransactionRepository` (LOY-4)."""

from __future__ import annotations

from backend.domain.commercial_instruments.entities.voucher_definition import VoucherDefinition
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_redemption import VoucherRedemption
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction
from backend.domain.commercial_instruments.enums import (
    VoucherInstanceStatus,
    VoucherTransactionStatus,
    VoucherTransactionType,
    VoucherType,
)
from backend.infrastructure.db.repositories.commercial_instruments.base import (
    CommercialInstrumentsRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class VoucherDefinitionRepository(CommercialInstrumentsRepositoryBase):
    def save(self, definition: VoucherDefinition) -> None:
        self._execute(
            """
            INSERT INTO voucher_definitions (
                id, code, name, voucher_type, active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, active=excluded.active, updated_at=excluded.updated_at
            """,
            (definition.id, definition.code, definition.name, definition.voucher_type.value,
             bool_to_int(definition.active), definition.created_at, definition.updated_at),
        )

    def get(self, definition_id: str) -> VoucherDefinition | None:
        row = self._query_one("SELECT * FROM voucher_definitions WHERE id=?", (definition_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> VoucherDefinition:
        return VoucherDefinition(
            id=row["id"], code=row["code"], name=row["name"],
            voucher_type=VoucherType(row["voucher_type"]), active=int_to_bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


class VoucherInstanceRepository(CommercialInstrumentsRepositoryBase):
    def save(self, instance: VoucherInstance) -> None:
        self._execute(
            """
            INSERT INTO voucher_instances (
                id, definition_id, code, status, customer_id, sale_id, issued_at,
                expires_at, closed_at, closed_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                sale_id=excluded.sale_id,
                closed_at=excluded.closed_at,
                closed_reason=excluded.closed_reason
            """,
            (
                instance.id, instance.definition_id, instance.code, instance.status.value,
                instance.customer_id, instance.sale_id, instance.issued_at,
                instance.expires_at, instance.closed_at, instance.closed_reason,
            ),
        )

    def get(self, instance_id: str) -> VoucherInstance | None:
        row = self._query_one("SELECT * FROM voucher_instances WHERE id=?", (instance_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> VoucherInstance | None:
        row = self._query_one("SELECT * FROM voucher_instances WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> VoucherInstance:
        return VoucherInstance(
            id=row["id"], definition_id=row["definition_id"], code=row["code"],
            status=VoucherInstanceStatus(row["status"]), customer_id=row["customer_id"],
            sale_id=row["sale_id"], issued_at=row["issued_at"], expires_at=row["expires_at"],
            closed_at=row["closed_at"], closed_reason=row["closed_reason"],
        )


class VoucherTransactionRepository(CommercialInstrumentsRepositoryBase):
    def save(self, transaction: VoucherTransaction) -> None:
        self._execute(
            """
            INSERT INTO voucher_transactions (
                id, voucher_instance_id, transaction_type, amount, status, operation_id,
                sale_id, reversal_transaction_id, reason_code, notes, created_by_user_id,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                reversal_transaction_id=excluded.reversal_transaction_id
            """,
            (
                transaction.id, transaction.voucher_instance_id,
                transaction.transaction_type.value, dec_str(transaction.amount),
                transaction.status.value, transaction.operation_id, transaction.sale_id,
                transaction.reversal_transaction_id, transaction.reason_code,
                transaction.notes, transaction.created_by_user_id, transaction.created_at,
            ),
        )

    def get(self, transaction_id: str) -> VoucherTransaction | None:
        row = self._query_one(
            "SELECT * FROM voucher_transactions WHERE id=?", (transaction_id,))
        return self._hydrate(row) if row else None

    def list_for_instance(self, voucher_instance_id: str) -> list[VoucherTransaction]:
        rows = self._query(
            "SELECT * FROM voucher_transactions WHERE voucher_instance_id=?"
            " ORDER BY created_at", (voucher_instance_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> VoucherTransaction:
        return VoucherTransaction(
            id=row["id"], voucher_instance_id=row["voucher_instance_id"],
            transaction_type=VoucherTransactionType(row["transaction_type"]),
            amount=to_decimal(row["amount"]), operation_id=row["operation_id"],
            status=VoucherTransactionStatus(row["status"]), sale_id=row["sale_id"],
            reversal_transaction_id=row["reversal_transaction_id"],
            reason_code=row["reason_code"], notes=row["notes"],
            created_by_user_id=row["created_by_user_id"], created_at=row["created_at"],
        )


class VoucherRedemptionRepository(CommercialInstrumentsRepositoryBase):
    def add(self, redemption: VoucherRedemption) -> None:
        self._execute(
            """
            INSERT INTO voucher_redemptions (
                id, voucher_instance_id, sale_id, amount_applied, redeemed_by_user_id,
                redeemed_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (redemption.id, redemption.voucher_instance_id, redemption.sale_id,
             dec_str(redemption.amount_applied), redemption.redeemed_by_user_id,
             redemption.redeemed_at),
        )

    def list_for_instance(self, voucher_instance_id: str) -> list[VoucherRedemption]:
        rows = self._query(
            "SELECT * FROM voucher_redemptions WHERE voucher_instance_id=?"
            " ORDER BY redeemed_at", (voucher_instance_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> VoucherRedemption:
        return VoucherRedemption(
            id=row["id"], voucher_instance_id=row["voucher_instance_id"],
            sale_id=row["sale_id"], amount_applied=to_decimal(row["amount_applied"]),
            redeemed_by_user_id=row["redeemed_by_user_id"], redeemed_at=row["redeemed_at"],
        )
