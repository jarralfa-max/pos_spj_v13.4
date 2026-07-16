"""Domain exceptions for the finance bounded context."""

from __future__ import annotations


class FinanceDomainError(Exception):
    """Base error for every finance domain violation."""


class CurrencyMismatchError(FinanceDomainError):
    """Raised when two Money values of different currencies are combined."""


class InvalidMoneyError(FinanceDomainError):
    """Raised when a monetary amount cannot be constructed safely."""


class UnbalancedEntryError(FinanceDomainError):
    """Raised when total debits differ from total credits."""


class EmptyEntryError(FinanceDomainError):
    """Raised when a journal entry has no lines or a line with zero amount."""


class ImmutableEntryError(FinanceDomainError):
    """Raised when a POSTED/REVERSED entry is mutated instead of reversed."""


class InvalidEntryStateError(FinanceDomainError):
    """Raised on an illegal journal-entry state transition."""


class PeriodClosedError(FinanceDomainError):
    """Raised when posting into a SOFT_CLOSED/CLOSED fiscal period."""


class PeriodStateError(FinanceDomainError):
    """Raised on an illegal fiscal-period state transition."""


class PeriodNotFoundError(FinanceDomainError):
    """Raised when no fiscal period covers a posting date."""


class DuplicateOperationError(FinanceDomainError):
    """Raised when an operation_id or posting purpose was already processed."""


class PostingProfileNotFoundError(FinanceDomainError):
    """Raised when no posting profile matches an economic event."""


class PostingAccountNotConfiguredError(FinanceDomainError):
    """Raised when a posting profile lacks a required account role."""


class AccountNotPostableError(FinanceDomainError):
    """Raised when posting to an account with posting_allowed = False."""


class CreditPolicyViolationError(FinanceDomainError):
    """Raised when a credit sale violates the customer credit policy."""


class PaymentAuthorizationError(FinanceDomainError):
    """Raised when a supplier payment skips or violates authorization."""


class ReconciliationError(FinanceDomainError):
    """Raised on invalid reconciliation transitions or unmatched amounts."""


class BudgetControlError(FinanceDomainError):
    """Raised when a commitment/accrual exceeds available budget under blocking control."""


class ObligationStateError(FinanceDomainError):
    """Raised on an illegal commercial-obligation transition (e.g. double redemption)."""


class ObligationAmountError(FinanceDomainError):
    """Raised when redeeming/releasing more than the outstanding obligation."""


class ReversalError(FinanceDomainError):
    """Raised when a reversal violates the reversal policy."""


class InsufficientOutstandingError(FinanceDomainError):
    """Raised when applying more than the outstanding amount of a document."""


class MaterialDifferenceError(FinanceDomainError):
    """Raised when closing a period with unjustified material differences."""
