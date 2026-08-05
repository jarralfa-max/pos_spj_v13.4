"""Cash Register security and policy errors."""


class CashRegisterError(Exception):
    """Base error for the Cash Register bounded context."""


class CashConfigurationError(CashRegisterError):
    pass


class CashPermissionDeniedError(CashRegisterError):
    pass


class CashAuthorizationRequiredError(CashRegisterError):
    pass


class CashLimitExceededError(CashRegisterError):
    pass


class CashSegregationOfDutiesError(CashRegisterError):
    pass


class CashInvalidStateError(CashRegisterError):
    pass


class CashDuplicateOperationError(CashRegisterError):
    pass

