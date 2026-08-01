class LogisticsDomainError(Exception):
    pass


class InvalidContainerHierarchyError(LogisticsDomainError):
    pass


class ContainerCapacityError(LogisticsDomainError):
    pass


class InvalidLogisticsStateError(LogisticsDomainError):
    pass
