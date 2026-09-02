"""LoyaltyTransactionRepository — persists/reconstructs the append-only
points ledger (`loyalty_transactions`).

``save()`` only ever INSERTs a brand-new row OR updates the two fields the
domain entity allows to mutate after creation (``status``,
``reversal_transaction_id``) — never ``points_amount``/``transaction_type``/
``operation_id`` (see ``backend/domain/loyalty/entities/
loyalty_transaction.py``'s own docstring: "No modificar movimientos
originales"). The ``ON CONFLICT`` clause deliberately excludes every other
column so a caller can never silently rewrite ledger history through this
repository, even by accident.
"""

from __future__ import annotations

from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import TransactionStatus, TransactionType
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    dec_str,
    to_decimal,
)


class LoyaltyTransactionRepository(LoyaltyRepositoryBase):
    def save(self, transaction: LoyaltyTransaction) -> None:
        self._execute(
            """
            INSERT INTO loyalty_transactions (
                id, loyalty_account_id, membership_id, transaction_type, points_amount,
                status, operation_id, source_module, source_document_type,
                source_document_id, sale_id, branch_id, reversal_transaction_id,
                reason_code, notes, created_by_user_id, available_at, expires_at,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                reversal_transaction_id=excluded.reversal_transaction_id
            """,
            (
                transaction.id, transaction.loyalty_account_id, transaction.membership_id,
                transaction.transaction_type.value, dec_str(transaction.points_amount),
                transaction.status.value, transaction.operation_id,
                transaction.source_module, transaction.source_document_type,
                transaction.source_document_id, transaction.sale_id, transaction.branch_id,
                transaction.reversal_transaction_id, transaction.reason_code,
                transaction.notes, transaction.created_by_user_id,
                transaction.available_at, transaction.expires_at, transaction.created_at,
            ),
        )

    def get(self, transaction_id: str) -> LoyaltyTransaction | None:
        row = self._query_one(
            "SELECT * FROM loyalty_transactions WHERE id=?", (transaction_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> LoyaltyTransaction | None:
        row = self._query_one(
            "SELECT * FROM loyalty_transactions WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def exists_for_source(
        self, *, source_module: str, source_document_id: str | None,
        transaction_type: TransactionType, reason_code: str | None,
    ) -> bool:
        """Idempotency probe mirroring the schema's own
        ``UNIQUE(source_module, source_document_id, transaction_type,
        reason_code)`` constraint (§12) — lets a use case check-before-write
        with a clear domain error instead of catching a raw
        ``sqlite3.IntegrityError``."""
        return self._scalar(
            "SELECT 1 FROM loyalty_transactions WHERE source_module=?"
            " AND source_document_id IS ? AND transaction_type=? AND reason_code IS ?",
            (source_module, source_document_id, transaction_type.value, reason_code),
        ) is not None

    def list_for_account(self, loyalty_account_id: str) -> list[LoyaltyTransaction]:
        """The full ledger for one account, oldest first — what
        ``LoyaltyBalancePolicy.balance()`` replays to reconstruct the
        current position (§11: never a second source of truth)."""
        rows = self._query(
            "SELECT * FROM loyalty_transactions WHERE loyalty_account_id=?"
            " ORDER BY created_at", (loyalty_account_id,))
        return [self._hydrate(row) for row in rows]

    def list_reserved_for_account(self, loyalty_account_id: str) -> list[LoyaltyTransaction]:
        rows = self._query(
            "SELECT * FROM loyalty_transactions WHERE loyalty_account_id=?"
            " AND transaction_type=? AND status=? ORDER BY created_at",
            (loyalty_account_id, TransactionType.RESERVE.value, TransactionStatus.RESERVED.value))
        return [self._hydrate(row) for row in rows]

    def list_expirable(self, *, before_iso: str, limit: int = 500) -> list[LoyaltyTransaction]:
        """AVAILABLE transactions whose ``expires_at`` has already passed —
        the read side of a future expiration sweep use case."""
        rows = self._query(
            "SELECT * FROM loyalty_transactions WHERE status=? AND expires_at IS NOT NULL"
            " AND expires_at < ? ORDER BY expires_at LIMIT ?",
            (TransactionStatus.AVAILABLE.value, before_iso, limit))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyTransaction:
        return LoyaltyTransaction(
            id=row["id"], loyalty_account_id=row["loyalty_account_id"],
            membership_id=row["membership_id"],
            transaction_type=TransactionType(row["transaction_type"]),
            points_amount=to_decimal(row["points_amount"]),
            operation_id=row["operation_id"], status=TransactionStatus(row["status"]),
            source_module=row["source_module"],
            source_document_type=row["source_document_type"],
            source_document_id=row["source_document_id"], sale_id=row["sale_id"],
            branch_id=row["branch_id"],
            reversal_transaction_id=row["reversal_transaction_id"],
            reason_code=row["reason_code"], notes=row["notes"],
            created_by_user_id=row["created_by_user_id"],
            available_at=row["available_at"], expires_at=row["expires_at"],
            created_at=row["created_at"],
        )
