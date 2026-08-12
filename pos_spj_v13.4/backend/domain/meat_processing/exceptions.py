"""Domain errors for Meat Processing security and invariants."""


class MeatProcessingError(Exception):
    """Base error for the Meat Processing bounded context."""


class MeatProcessingConfigurationError(MeatProcessingError):
    pass


class MeatProcessingPermissionDeniedError(MeatProcessingError):
    pass


class MeatProcessingScopeError(MeatProcessingPermissionDeniedError):
    pass


class MeatProcessingSegregationOfDutiesError(MeatProcessingPermissionDeniedError):
    pass


class MeatProcessingInvariantError(MeatProcessingError):
    pass


class MeatProcessingStateTransitionError(MeatProcessingInvariantError):
    pass
