"""Typed domain errors for payment intents."""


class PaymentDomainError(ValueError):
    """Base class for invalid payment-intent operations."""


class PaymentIntentTransitionError(PaymentDomainError):
    """The requested transition is not allowed from the current state."""


class PaymentConfirmationMismatchError(PaymentDomainError):
    """Provider confirmation does not match the persisted intent."""
