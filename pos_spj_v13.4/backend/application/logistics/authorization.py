class LogisticsPermissionDeniedError(PermissionError):
    pass


class LogisticsAuthorizationPolicy:
    def __init__(self, checker=None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission: str) -> None:
        if self._checker is None or not user_id or not self._checker.has_permission(user_id, permission):
            raise LogisticsPermissionDeniedError(f"Permiso requerido: {permission}")


class LogisticsPermissions:
    SHIPMENT_VIEW = "logistics.shipment.view"
    SHIPMENT_CREATE = "logistics.shipment.create"
    CONTAINER_MANAGE = "logistics.container.manage"
    CONTAINER_ATTACH = "logistics.container.attach"
    CONTAINER_MOVE = "logistics.container.move"
    CONTAINER_SEAL = "logistics.container.seal"
    SHIPMENT_DISPATCH = "logistics.shipment.dispatch"
    SHIPMENT_OVERRIDE = "logistics.shipment.override"
    CONTAINER_RELEASE = "logistics.container.release"
    LABEL_PRINT = "logistics.label.print"
