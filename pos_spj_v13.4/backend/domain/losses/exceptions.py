"""Domain errors for Losses security and authorization."""


class LossError(Exception):
    """Base error for the Losses bounded context."""


class LossConfigurationError(LossError):
    pass


class LossPermissionDeniedError(LossError):
    pass


class LossScopeError(LossPermissionDeniedError):
    pass


class LossLimitExceededError(LossPermissionDeniedError):
    pass


class LossSegregationOfDutiesError(LossPermissionDeniedError):
    pass


class LossInvariantError(LossError):
    pass


class LossStateTransitionError(LossInvariantError):
    pass
