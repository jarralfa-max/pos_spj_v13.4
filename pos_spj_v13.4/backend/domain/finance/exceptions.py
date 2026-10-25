"""Domain exceptions for the finance bounded context (catálogo del prompt §34).

Cada error dice QUÉ regla se violó. Los mensajes son seguros para mostrarse al
usuario; un error inesperado (no ``FinanceDomainError``) se registra con su
traza y se muestra con un mensaje genérico, nunca se oculta.
"""

from __future__ import annotations


class FinanceDomainError(Exception):
    """Base error for every finance domain violation."""


# ── dinero / moneda ───────────────────────────────────────────────────────
class CurrencyMismatchError(FinanceDomainError):
    """Raised when two Money values of different currencies are combined."""


class InvalidMoneyError(FinanceDomainError):
    """Raised when a monetary amount cannot be constructed safely."""


class ExchangeRateNotFoundError(FinanceDomainError):
    """Raised when a foreign-currency operation has no rate for its date."""


# ── plan de cuentas ───────────────────────────────────────────────────────
class AccountNotFoundError(FinanceDomainError):
    """Raised when an account id/code does not exist."""


class AccountNotPostableError(FinanceDomainError):
    """Raised when posting to a summary (grouping) account."""


class AccountInactiveError(AccountNotPostableError):
    """Raised when posting to an inactive account."""


class AccountInUseError(FinanceDomainError):
    """Raised when a used account would change nature/type or be removed."""


# ── asientos ──────────────────────────────────────────────────────────────
class UnbalancedJournalEntryError(FinanceDomainError):
    """Raised when total debits differ from total credits."""


class EmptyEntryError(FinanceDomainError):
    """Raised when a journal entry has no lines or a line with zero amount."""


class InvalidEntryStateError(FinanceDomainError):
    """Raised on an illegal journal-entry state transition."""


class JournalEntryAlreadyPostedError(InvalidEntryStateError):
    """Raised when posting (or validating) an entry that is already POSTED."""


class JournalEntryImmutableError(FinanceDomainError):
    """Raised when a POSTED/REVERSED entry is mutated instead of reversed."""


class JournalEntryNotFoundError(FinanceDomainError):
    """Raised when a journal entry id does not exist."""


class ReversalError(FinanceDomainError):
    """Raised when a reversal violates the reversal policy."""


class JournalEntryAlreadyReversedError(ReversalError):
    """Raised when reversing an entry a second time (another operation)."""


class SegregationOfDutiesError(FinanceDomainError):
    """Raised when the same person would perform two incompatible steps."""


# ── periodos ──────────────────────────────────────────────────────────────
class ClosedFiscalPeriodError(FinanceDomainError):
    """Raised when posting into a SOFT_CLOSED/CLOSED fiscal period."""


class PeriodStateError(FinanceDomainError):
    """Raised on an illegal fiscal-period state transition."""


class PeriodNotFoundError(FinanceDomainError):
    """Raised when no fiscal period covers a posting date."""


class InvalidAccountingDateError(FinanceDomainError):
    """Raised when an accounting date is missing, malformed or outside its period."""


# ── idempotencia / concurrencia ───────────────────────────────────────────
class DuplicateOperationError(FinanceDomainError):
    """Raised when an operation_id or posting purpose was already processed."""


class IdempotencyConflictError(DuplicateOperationError):
    """Raised when an operation key is reused with different economic content."""


class ConcurrencyConflictError(FinanceDomainError):
    """Raised when a stale aggregate version is written (optimistic concurrency)."""


# ── configuración contable ────────────────────────────────────────────────
class PostingProfileNotFoundError(FinanceDomainError):
    """Raised when no posting profile matches an economic event."""


class PostingAccountNotConfiguredError(FinanceDomainError):
    """Raised when a posting profile lacks a required account role."""


class FinanceConfigurationError(FinanceDomainError):
    """Raised when a finance command is wired without its dependencies."""


class FinanceSchemaContractError(FinanceDomainError):
    """Raised when the database finance schema is not the born-clean contract."""


# ── cuentas por cobrar ────────────────────────────────────────────────────
class ReceivableNotFoundError(FinanceDomainError):
    """Raised when a receivable id does not exist."""


class InsufficientOutstandingError(FinanceDomainError):
    """Raised when applying more than the outstanding amount of a document."""


class CollectionAmountExceededError(InsufficientOutstandingError):
    """Raised when applications exceed the collection or the receivable balance."""


class CollectionAlreadyAppliedError(FinanceDomainError):
    """Raised when an application would be registered twice."""


class CreditPolicyViolationError(FinanceDomainError):
    """Raised when a credit sale violates the customer credit policy."""


class CreditLimitExceededError(CreditPolicyViolationError):
    """Raised when a credit sale exceeds the available credit."""


# ── cuentas por pagar ─────────────────────────────────────────────────────
class PayableNotFoundError(FinanceDomainError):
    """Raised when a payable id does not exist."""


class PaymentAuthorizationError(FinanceDomainError):
    """Raised when a supplier payment skips or violates authorization."""


class PaymentNotAuthorizedError(PaymentAuthorizationError):
    """Raised when executing a payment that is not (fully) authorized."""


class PaymentAlreadyExecutedError(PaymentAuthorizationError):
    """Raised when a payment would be executed twice."""


class SupplierDocumentBlockedError(FinanceDomainError):
    """Raised when paying a supplier document blocked by a receipt difference."""


# ── tesorería / conciliación ──────────────────────────────────────────────
class TreasuryAccountNotFoundError(FinanceDomainError):
    """Raised when a treasury account id does not exist (or is inactive)."""


class InsufficientTreasuryFundsError(FinanceDomainError):
    """Raised when a movement would overdraw a treasury account."""


class DuplicateTreasuryTransferError(DuplicateOperationError):
    """Raised when the same transfer is registered twice with other content."""


class ReconciliationError(FinanceDomainError):
    """Raised on invalid reconciliation transitions or unmatched amounts."""


class BankStatementAlreadyImportedError(ReconciliationError):
    """Raised when the same statement (same content) is imported again."""


class TransactionAlreadyReconciledError(ReconciliationError):
    """Raised when a statement line or ledger line is reconciled twice."""


class ReconciliationMismatchError(ReconciliationError):
    """Raised when a match pairs different amounts outside the tolerance."""


# ── presupuesto / gasto ───────────────────────────────────────────────────
class BudgetControlError(FinanceDomainError):
    """Raised when spending violates budget control."""


class BudgetNotApprovedError(BudgetControlError):
    """Raised when spending against a budget that does not control spending."""


class BudgetExceededError(BudgetControlError):
    """Raised when a commitment exceeds the blocking availability."""


class ExpenseNotAuthorizedError(FinanceDomainError):
    """Raised when an expense advances without its required approvals."""


# ── activos ───────────────────────────────────────────────────────────────
class DepreciationAlreadyPostedError(FinanceDomainError):
    """Raised when a depreciation run is repeated for a period with other content."""


class AssetNotActiveError(FinanceDomainError):
    """Raised when operating on an asset that is not ACTIVE."""


# ── instrumentos comerciales ──────────────────────────────────────────────
class ObligationStateError(FinanceDomainError):
    """Raised on an illegal commercial-obligation transition (e.g. double redemption)."""


class ObligationAmountError(FinanceDomainError):
    """Raised when redeeming/releasing more than the outstanding obligation."""


# ── cierre ────────────────────────────────────────────────────────────────
class MaterialDifferenceError(FinanceDomainError):
    """Raised when closing a period with unjustified material differences."""


# ── seguridad ─────────────────────────────────────────────────────────────
class PermissionDeniedError(FinanceDomainError):
    """Raised when the actor lacks the FINANZAS.<accion> permission (fail closed)."""
